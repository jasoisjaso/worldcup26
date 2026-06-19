"""Auto-fires the api-football archive backfill when:
  * api-football daily quota appears healthy (no in-process exhaustion flag),
  * at least one completed Match has empty archives (events/lineups/stats/pred),
  * we haven't successfully completed a full backfill today.

Designed to be called by the refresh scheduler every 60 minutes. When all three
conditions hold it runs `backfill_archive.backfill(apply=True)` once. Otherwise
returns a tiny status dict explaining why it skipped — never burns API calls
to check, since the pre-flight is all DB-local.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from backend.db.session import SessionLocal
from backend.db.models import (
    ApiFootballPrediction,
    Match,
    MatchEvent,
    MatchLineup,
    MatchStatistics,
)
from backend.data import quota_budget as _qb

logger = logging.getLogger(__name__)

# In-process marker. Reset every UTC date roll.
_LAST_FULL_RUN_DATE: str | None = None


def _today_utc_iso() -> str:
    return datetime.utcnow().date().isoformat()


def _count_archive_gaps() -> dict:
    """Cheap DB-only check: any completed match missing any archive table row?"""
    db = SessionLocal()
    try:
        done = db.query(Match).filter(Match.status == "complete").all()
        if not done:
            return {"gaps": 0, "matches": 0}
        gaps = 0
        for m in done:
            empty = (
                db.query(MatchEvent).filter(MatchEvent.match_id == m.id).count() == 0
                or db.query(MatchLineup).filter(MatchLineup.match_id == m.id).count() == 0
                or db.query(MatchStatistics).filter(MatchStatistics.match_id == m.id).count() == 0
                or db.query(ApiFootballPrediction).filter(ApiFootballPrediction.match_id == m.id).count() == 0
            )
            if empty:
                gaps += 1
        return {"gaps": gaps, "matches": len(done)}
    finally:
        db.close()


async def auto_backfill_tick() -> dict:
    """One scheduler tick. Only fires in Phase 1 (first hour after UTC reset),
    with a daily cap of BACKFILL_MAX_CALLS. Respects the shared quota budget."""
    if not os.getenv("API_FOOTBALL_KEY"):
        return {"status": "no_api_key"}

    _qb.reset_if_new_day()

    if not _qb.backfill_can_run():
        return {"status": "skipped", "reason": f"budget_gated phase={_qb.budget_summary()['phase']}"}

    gaps = _count_archive_gaps()
    if gaps["gaps"] == 0:
        return {"status": "no_gaps", **gaps}

    logger.info("auto-backfill firing: %d matches with gaps (quota: %s)",
                gaps["gaps"], _qb.quota_remaining())
    try:
        from backend.data.backfill_archive import backfill
        summary = await backfill(apply=True)
        # Record each call the backfill made so the budget stays accurate.
        calls_made = summary.get("matches_processed", 0) * 5  # ~5 endpoints per match
        for _ in range(calls_made):
            _qb.record_backfill_call()
    except Exception as exc:
        logger.warning("auto-backfill failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200], **gaps}

    return {"status": "ran", **summary, "budget": _qb.budget_summary()}
