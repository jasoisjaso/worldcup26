"""APScheduler jobs that keep data fresh without a deploy."""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.data.fetchers.results import refresh_form_cache
from backend.data.fetchers.elo import fetch_elo_ratings
from backend.data.fetchers.odds import refresh_odds_cache
from backend.data.fetchers.scores import refresh_scores
from backend.data.fetchers.suspensions import refresh_match_events
from backend.data.prediction_logger import log_upcoming_predictions
from backend.data.clv import update_closing_lines
from backend.data.tournament_cache import refresh_tournament
from backend.models.dc_ratings import ensure_fitted as ensure_dc_fitted
from backend.db.session import SessionLocal
from backend.db.models import Team

scheduler = AsyncIOScheduler(timezone="UTC")


async def _refresh_elo() -> None:
    try:
        ratings = await fetch_elo_ratings()
    except Exception:
        return

    db = SessionLocal()
    try:
        for entry in ratings:
            team = db.query(Team).filter(Team.name == entry["team_name"]).first()
            if team:
                team.elo = entry["elo"]
        db.commit()
    finally:
        db.close()


def start_scheduler() -> None:
    scheduler.add_job(refresh_form_cache, "interval", hours=6, id="form_refresh")
    # Re-fit Dixon-Coles so ratings track results through the tournament instead of
    # freezing at boot (ensure_fitted self-skips until its 12h cache is stale).
    scheduler.add_job(ensure_dc_fitted, "interval", hours=12, id="dc_refit")
    scheduler.add_job(_refresh_elo, "interval", hours=24, id="elo_refresh")
    scheduler.add_job(refresh_odds_cache, "interval", hours=4, id="odds_refresh")
    scheduler.add_job(refresh_scores, "interval", minutes=30, id="score_refresh")
    scheduler.add_job(refresh_match_events, "interval", hours=2, id="match_events")
    scheduler.add_job(log_upcoming_predictions, "interval", minutes=30, id="pred_logger")
    # Capture the closing line for logged picks near kickoff (CLV tracking)
    scheduler.add_job(update_closing_lines, "interval", minutes=20, id="clv_capture")
    # Keep the tournament projection warm (recompute self-skips via its own cache signature)
    scheduler.add_job(refresh_tournament, "interval", minutes=30, id="tournament_sim")
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
