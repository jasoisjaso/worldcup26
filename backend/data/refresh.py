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
from backend.betting.multi_picker import generate_daily_picks as _gen_picks, settle_finished_multis as _settle_picks
from backend.data.fetchers.injuries_persist import refresh_team_injuries as _refresh_injuries
from backend.data.calibration_logger import log_finished_matches as _log_calibration
from backend.data.auto_backfill import auto_backfill_tick as _auto_backfill_tick


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
    ("harvester", _run_harvester_once, 5, "Background harvester"),
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
]


# Register at import so /health knows the full feed set even before the scheduler starts.
for _fid, _fn, _interval, _label in _JOBS:
    feed_health.register(_fid, _label, _interval)


def start_scheduler() -> None:
    for feed_id, fn, interval_min, _label in _JOBS:
        scheduler.add_job(_tracked(feed_id, fn), "interval", minutes=interval_min, id=feed_id)
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
