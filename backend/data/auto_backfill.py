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
    """One scheduler tick. Returns a status dict that surfaces on /health."""
    global _LAST_FULL_RUN_DATE
    if not os.getenv("API_FOOTBALL_KEY"):
        return {"status": "no_api_key"}

    # Already ran a full pass today — don't re-run until the date rolls.
    today = _today_utc_iso()
    if _LAST_FULL_RUN_DATE == today:
        return {"status": "already_ran_today"}

    # Reuse the harvester's quota-exhaustion marker so we don't waste a probe.
    try:
        from backend.data.harvester import _QUOTA_EXHAUSTED_DATE
        if _QUOTA_EXHAUSTED_DATE == today:
            return {"status": "skipped", "reason": "harvester_quota_exhausted"}
    except Exception:
        pass

    gaps = _count_archive_gaps()
    if gaps["gaps"] == 0:
        # Nothing to backfill. Mark as ran-today so we don't keep counting.
        _LAST_FULL_RUN_DATE = today
        return {"status": "no_gaps", **gaps}

    # Run the backfill end-to-end. backfill_archive handles its own per-fixture
    # error recovery + quota-exhausted body detection at the request level.
    logger.info("auto-backfill firing: %d matches with gaps", gaps["gaps"])
    try:
        from backend.data.backfill_archive import backfill
        summary = await backfill(apply=True)
    except Exception as exc:
        logger.warning("auto-backfill failed: %s", exc)
        return {"status": "error", "error": str(exc)[:200], **gaps}

    # If we processed at least one match successfully OR hit a quota wall,
    # mark today done so we don't keep retrying within the same UTC day.
    if summary.get("matches_processed", 0) > 0 or "error" in summary:
        _LAST_FULL_RUN_DATE = today

    return {"status": "ran", **summary}
