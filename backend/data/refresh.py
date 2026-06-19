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
from backend.data.fetchers.topscorers import refresh_topscorers
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
    ("dc_refit", ensure_dc_fitted, 12 * 60, "Dixon-Coles ratings fit"),
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
