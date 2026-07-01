"""APScheduler jobs that keep data fresh without a deploy."""
import inspect
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.data.fetchers.results import refresh_form_cache, name_to_code
from backend.data.fetchers.elo import fetch_elo_ratings
from backend.data.fetchers.odds import refresh_odds_cache, refresh_near_kickoff
from backend.data.fetchers.scores import refresh_scores
from backend.data.fetchers.suspensions import refresh_match_events
from backend.data.fetchers.live import refresh_live_fixtures
from backend.data.fetchers.prematch import prefetch_pending_matches
from backend.data.fetchers.topscorers import refresh_topscorers
from backend.data.harvester import run_one_pass as _run_harvester_once
from backend.data.fetchers.sharp_odds import refresh_sharp_odds as _refresh_sharp_odds
from backend.data.ht_score_backfill import backfill_all as _backfill_ht
from backend.data.score_sanity import audit_match_scores as _audit_scores
from backend.data.harvester_seed import seed_heavy as _heavy_seed, seed_upcoming_odds as _seed_upcoming_odds
from backend.data import quota_budget as _qb
from backend.betting.multi_picker import generate_daily_picks as _gen_picks, settle_finished_multis as _settle_picks
from backend.data.fetchers.injuries_persist import refresh_team_injuries as _refresh_injuries
from backend.data.calibration_logger import log_finished_matches as _log_calibration
from backend.data.auto_backfill import auto_backfill_tick as _auto_backfill_tick
from backend.data.harvest_processor import run_one_pass as _run_processor_once


async def _model_picks_tick() -> dict:
    """Combined tick: settle anything finished first, then top up with new picks if low."""
    settled = _settle_picks()
    generated = _gen_picks()
    return {"settled": settled, "generated": generated}


async def _calibration_tick() -> dict:
    """Log per-match calibration for any newly-completed match.
    Read-only on the API — pure DB work — so this is cheap to run frequently."""
    return _log_calibration()
from backend.data.aggregations import rebuild_aggregations
from backend.data.prediction_logger import log_upcoming_predictions
from backend.data.clv import update_closing_lines
from backend.data.tournament_cache import refresh_tournament
from backend.data import feed_health
from backend.models.dc_ratings import ensure_fitted as ensure_dc_fitted
from backend.db.session import SessionLocal
from backend.db.models import Team

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler(timezone="UTC")


async def _refresh_elo() -> None:
    try:
        ratings = await fetch_elo_ratings()
    except Exception:
        return

    db = SessionLocal()
    try:
        unmatched = []
        for entry in ratings:
            # Resolve by tolerant code lookup, not exact name string: a scrape rename or
            # a dropped accent (e.g. "Cote d'Ivoire" vs "Côte d'Ivoire") must not silently
            # freeze a team at its seed ELO for the whole tournament.
            code = name_to_code(entry["team_name"])
            team = db.query(Team).filter(Team.code == code).first() if code else None
            if team is None:
                team = db.query(Team).filter(Team.name == entry["team_name"]).first()
            if team:
                team.elo = entry["elo"]
            else:
                unmatched.append(entry["team_name"])
        db.commit()
        if unmatched:
            logger.warning("ELO refresh: %d source team(s) unmatched: %s", len(unmatched), unmatched[:10])
    finally:
        db.close()


def _tracked(feed_id: str, fn):
    """Wrap a job so it records a feed-health success only when it completes cleanly."""
    async def wrapper():
        result = fn()
        if inspect.isawaitable(result):
            result = await result
        feed_health.record(feed_id)
        return result
    wrapper.__name__ = getattr(fn, "__name__", feed_id)
    return wrapper


def _auto_heavy_seed_tick() -> dict:
    """Fire heavy seed once daily at 20:00 UTC if quota > 30k."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    if now.hour != 20:
        return {"status": "skipped", "reason": "not_20utc"}
    from backend.db.session import SessionLocal
    from backend.db.models import HarvestErrorLog
    db = SessionLocal()
    try:
        already = db.query(HarvestErrorLog).filter(
            HarvestErrorLog.endpoint == "heavy_seed",
            HarvestErrorLog.error_type == "fired",
            HarvestErrorLog.logged_at >= datetime(now.year, now.month, now.day, 0, 0, 0),
        ).first()
        if already:
            return {"status": "skipped", "reason": "already_fired_today"}
        remaining = _qb.quota_remaining() or 0
        if remaining < 30000:
            return {"status": "skipped", "reason": f"quota_below_30k ({remaining})"}
        result = _heavy_seed()
        db.add(HarvestErrorLog(
            endpoint="heavy_seed", error_type="fired",
            error_msg=f"added {result.get('total_jobs_added', 0)} jobs at quota={remaining}"
        ))
        db.commit()
        return result
    finally:
        db.close()


async def _harvester_tick() -> dict:
    """Phase-2 harvester tick: drain a tier-sized batch of jobs per call.

    The batch size comes from quota_budget.harvester_batch_size(), which is
    tiered by remaining quota. At the fast tier (10 jobs/tick × 6 ticks/min)
    this gives the ~3,600 calls/h steady burn the operator wants, instead of
    the old one-job-per-tick cap (~360/h). We re-check the gate before each
    job so a mid-batch quota drop or a drained queue stops us immediately.
    """
    batch = _qb.harvester_batch_size()
    if batch <= 0:
        return {"status": "skipped", "reason": "gated_or_no_quota"}
    ran = 0
    last = None
    for _ in range(batch):
        if _qb.harvester_batch_size() <= 0:
            break  # quota crossed a tier floor mid-batch — stop
        last = await _run_harvester_once()
        if (last or {}).get("status") in {"idle", "skipped"}:
            break  # queue drained or gated — no point hammering further
        ran += 1
    return {"status": "harvested", "jobs_this_tick": ran, "last": last}


async def _push_dispatch_tick() -> dict:
    """Scheduler wrapper around backend.data.push_dispatch.

    Kept as a thin tick so the heavy module isn't imported at refresh.py
    load time — keeps cold-start cost off the import path.
    """
    from backend.data.push_dispatch import dispatch_pending_events
    return dispatch_pending_events()


# (feed_id, job, interval_minutes, label)
_JOBS = [
    ("form_refresh", refresh_form_cache, 6 * 60, "Recent results / form"),
    # During WC: refit every 3 hours so each new result re-shapes the priors
    # within a couple of matches, not the next morning.
    ("dc_refit", ensure_dc_fitted, 180, "Dixon-Coles ratings fit"),
    ("elo_refresh", _refresh_elo, 24 * 60, "ELO ratings"),
    ("odds_refresh", refresh_odds_cache, 8 * 60, "Bookmaker odds"),
    # Pre-kickoff forced odds refresh — bypasses the 8h TTL when a match
    # starts within 90 min and the cache is >45 min old. Makes the CLV
    # closing-line capture a real near-closing line and un-stales the
    # homepage EV during match windows. ~4 Odds API credits per kickoff
    # cluster; a free no-op the rest of the day.
    ("odds_prekickoff", refresh_near_kickoff, 10, "Pre-kickoff odds refresh"),
    # Forward odds capture from api-football — enqueues one /odds job per
    # watched league per day (7-day lookahead, dedup per date). api-football
    # expires odds ~14 days post-match, so this rolling capture is the ONLY
    # way to build the odds archive the EPL/club-league models will need.
    ("odds_harvest_seed", _seed_upcoming_odds, 6 * 60, "Forward odds capture seed"),
    ("score_refresh", refresh_scores, 30, "Match results"),
    ("match_events", refresh_match_events, 2 * 60, "Cards / suspensions"),
    ("pred_logger", log_upcoming_predictions, 30, "Pre-kickoff prediction log"),
    ("clv_capture", update_closing_lines, 20, "Closing-line capture (CLV)"),
    ("tournament_sim", refresh_tournament, 30, "Tournament simulation"),
    # Live in-play polling — runs every 30 seconds. Cheap when nothing is live (one
    # /fixtures?live=all call). Drives the swing chart, event ticker, and big-moment
    # push triggers when matches are in progress.
    ("live_feed", refresh_live_fixtures, 0.5, "Live in-play feed"),  # 30s interval
    ("topscorers", refresh_topscorers, 60, "Golden Boot leaderboard"),
    # Pre-match prefetch: prediction + lineup + h2h snapshots, captured once per match.
    # Each cached forever after that. Cheap when nothing's pending.
    ("prematch_prefetch", prefetch_pending_matches, 15, "Pre-match prefetcher"),
    # Aggregations: rebuild player + team season stats from the persistent archive.
    # Zero API cost; runs every 10min and after every FT.
    ("aggregations", rebuild_aggregations, 10, "Player + team aggregations"),
    # Data harvester: scrapes anything spare api-football quota will allow into
    # our long-term archive. Self-throttles below the live-reserve floor.
    # 10s interval × a quota-tier batch (quota_budget.harvester_batch_size):
    # fast tier = 10 jobs/tick → ~3,600 calls/h steady burn (2026-06-22 fix —
    # was one job/tick = ~360/h, which left most of the 75k Ultra budget unused).
    ("harvester", _harvester_tick, 10.0 / 60.0, "Background harvester"),
    # Daily model-picked multis + settle anything that's now complete.
    ("model_multis", _model_picks_tick, 30, "Model-picked multis"),
    # Persistent injury layer — 48 calls per cycle, every 6 hours.
    ("injuries_persist", _refresh_injuries, 6 * 60, "Persistent injury layer"),
    # Calibration logger: zero-API cost, runs every 10 min after scores update.
    ("calibration", _calibration_tick, 10, "Per-match calibration log"),
    # Auto-backfill: hourly poll that fires the api-football archive walker the
    # moment quota allows + completed matches still have empty archives. Skips
    # itself once it has run successfully today. ~140 API calls when it does fire.
    ("auto_backfill", _auto_backfill_tick, 60, "Auto archive backfill"),
    # Harvest processor: reads unprocessed HarvestRaw blobs and normalises them
    # into PlayerProfile, FixtureArchive, PlayerHistory, etc. Zero API cost —
    # only DB work. Runs every 10 minutes, 5 blobs per pass.
    ("harvest_processor", _run_processor_once, 10, "Harvest post-processor"),
    # Sharp odds (Pinnacle via SportsGameOdds free tier): one call returns the
    # full slate. Every 6h = ~120 calls/month against the 1,000/mo budget.
    # Module no-ops without SPORTSGAMEODDS_API_KEY so local dev is safe.
    ("sharp_odds", _refresh_sharp_odds, 6 * 60, "Sharp odds (Pinnacle)"),
    # Half-time score backfill — reads our /fixtures HarvestRaw blobs and
    # populates Match.home_ht_score / away_ht_score. Zero API cost (pure DB
    # read). Hourly is plenty; the blob set only grows when the harvester
    # completes new league seeds.
    ("ht_backfill", _backfill_ht, 60, "Half-time score backfill"),
    # Score-sanity audit — compares stored Match FT vs MatchEvent goal totals
    # every 15 min. Auto-fixes orientation swaps (safe, magnitude-preserving)
    # and ALERTS on magnitude mismatches (operator review — events may be
    # incomplete). Born from the 2026-06-21 incident where the Odds API
    # path matched a HISTORICAL Haiti 1-0 Scotland friendly and overwrote
    # our WC fixture.
    ("score_sanity", _audit_scores, 15, "Score-vs-events sanity audit"),
    # Heavy seed — fires once daily at 20:00 UTC if quota > 30k remaining.
    # Queues 200k+ harvest jobs across all leagues/endpoints. Idempotent
    # (dedup prevents double-queuing). Checked every 60 min, but only fires
    # at hour 20. Skip creates a marker in HarvestErrorLog so it fires
    # exactly once per UTC day.
    ("heavy_seed", _auto_heavy_seed_tick, 60, "Auto heavy seed (daily 20:00 UTC)"),
    # Follow-match notification dispatcher — scans MatchEvent + Match for
    # goals/reds/HT/FT/penalty/VAR/suspended/resumed and fires push
    # notifications to subscribers per their event_mask. Reads only,
    # decoupled from the live poller (which the shootout-tracking agent
    # owns). 60s interval gives the 30s goal-confirm queue room to
    # mitigate the FotMob wrong-player-id race. Zero API cost (all DB).
    ("push_dispatch", _push_dispatch_tick, 1, "Follow-match push dispatch"),
]


# Register at import so /health knows the full feed set even before the scheduler starts.
for _fid, _fn, _interval, _label in _JOBS:
    feed_health.register(_fid, _label, _interval)


async def _harvester_burn_tick() -> dict:
    """5-sec burst tick that fires only inside the Phase 3 burn window.

    Outside Phase 3 (or when paused) this is a cheap no-op. Inside the
    window it drains the harvest queue at BURN_BATCH_PER_TICK jobs per second
    — combined with the normal harvester tick this lets us cleanly empty the
    reserved calls without ever touching concurrency at the queue level.
    Honours the same gates as the main harvester (quota floor, pause flag),
    just with a different time-of-day filter. The per-job burn_should_fire()
    re-check inside the loop means we stop the instant quota crosses the
    floor mid-batch.
    """
    if not _qb.burn_should_fire():
        return {"status": "skipped", "reason": "outside_burn_window"}
    ran = 0
    last = None
    for _ in range(_qb.BURN_BATCH_PER_TICK):
        if not _qb.burn_should_fire():
            break  # quota crossed the floor mid-batch — stop immediately
        last = await _run_harvester_once()
        if (last or {}).get("status") in {"idle", "skipped"}:
            break  # queue drained or gated — no point hammering further this tick
        ran += 1
    return {"status": "burned", "jobs_this_tick": ran, "last": last}


# The burn-mode tick is registered separately from _JOBS because it runs on a
# seconds-grained interval (APScheduler accepts both, but the rest of the
# scheduler uses the minutes column). It does NOT register a feed-health entry
# — burn is a fan-out of the main "harvester" feed and shouldn't trip its
# staleness alarm on quiet days.

# Burn-window tick: 1s. At BURN_BATCH_PER_TICK (3) jobs per tick that's
# 180 calls/min — 40% under api-football's 300/min cap. Over a 3h burn window
# that can drain ~32k calls if the queue is deep. Combined with the regular
# harvester tick this clears meaningful quota before UTC midnight. The batch
# loop self-limits: it stops the moment the queue empties or quota hits the floor.
_BURN_INTERVAL_SECONDS = 1


def start_scheduler() -> None:
    for feed_id, fn, interval_min, _label in _JOBS:
        scheduler.add_job(_tracked(feed_id, fn), "interval", minutes=interval_min, id=feed_id)
    scheduler.add_job(_harvester_burn_tick, "interval", seconds=_BURN_INTERVAL_SECONDS, id="harvester_burn")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
