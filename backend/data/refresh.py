"""APScheduler jobs that keep data fresh without a deploy."""
import inspect
import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.data.fetchers.results import refresh_form_cache, name_to_code
from backend.data.fetchers.elo import fetch_elo_ratings
from backend.data.fetchers.odds import refresh_odds_cache
from backend.data.fetchers.scores import refresh_scores
from backend.data.fetchers.suspensions import refresh_match_events
from backend.data.fetchers.live import refresh_live_fixtures
from backend.data.fetchers.prematch import prefetch_pending_matches
from backend.data.fetchers.topscorers import refresh_topscorers
from backend.data.harvester import run_one_pass as _run_harvester_once
from backend.data.fetchers.sharp_odds import refresh_sharp_odds as _refresh_sharp_odds
from backend.data import quota_budget as _qb
from backend.betting.multi_picker import generate_daily_picks as _gen_picks, settle_finished_multis as _settle_picks
from backend.data.fetchers.injuries_persist import refresh_team_injuries as _refresh_injuries
from backend.data.calibration_logger import log_finished_matches as _log_calibration
from backend.data.auto_backfill import auto_backfill_tick as _auto_backfill_tick
from backend.data.harvest_processor import run_one_pass as _run_processor_once
from backend.data.harvester_seed import seed_full_stack as _seed_full_stack


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


# (feed_id, job, interval_minutes, label)
_JOBS = [
    ("form_refresh", refresh_form_cache, 6 * 60, "Recent results / form"),
    # During WC: refit every 3 hours so each new result re-shapes the priors
    # within a couple of matches, not the next morning.
    ("dc_refit", ensure_dc_fitted, 180, "Dixon-Coles ratings fit"),
    ("elo_refresh", _refresh_elo, 24 * 60, "ELO ratings"),
    ("odds_refresh", refresh_odds_cache, 8 * 60, "Bookmaker odds"),
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
    # 1-min interval gives ~60 calls/hr when quota is healthy; quota_budget
    # pacing tiers (FAST_ABOVE / SLOW_BELOW) drop the cadence as the budget tightens.
    ("harvester", _run_harvester_once, 1, "Background harvester"),
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
]


# Register at import so /health knows the full feed set even before the scheduler starts.
for _fid, _fn, _interval, _label in _JOBS:
    feed_health.register(_fid, _label, _interval)


async def _harvester_burn_tick() -> dict:
    """5-sec burst tick that fires only inside the Phase 3 burn window.

    Outside Phase 3 (or when paused) this is a cheap no-op. Inside the
    window it drains the harvest queue 12 times per minute — combined with
    the normal 1/min job this lets us cleanly empty 1,250 reserved calls in
    a few minutes without ever touching concurrency at the queue level.
    Honours the same gates as the main harvester (quota floor, pause flag),
    just with a different time-of-day filter.
    """
    if not _qb.burn_should_fire():
        return {"status": "skipped", "reason": "outside_burn_window"}
    return await _run_harvester_once()


# The burn-mode tick is registered separately from _JOBS because it runs on a
# seconds-grained interval (APScheduler accepts both, but the rest of the
# scheduler uses the minutes column). It does NOT register a feed-health entry
# — burn is a fan-out of the main "harvester" feed and shouldn't trip its
# staleness alarm on quiet days.

_BURN_INTERVAL_SECONDS = 5


def start_scheduler() -> None:
    for feed_id, fn, interval_min, _label in _JOBS:
        scheduler.add_job(_tracked(feed_id, fn), "interval", minutes=interval_min, id=feed_id)
    scheduler.add_job(_harvester_burn_tick, "interval", seconds=_BURN_INTERVAL_SECONDS, id="harvester_burn")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
