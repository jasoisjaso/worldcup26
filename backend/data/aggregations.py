"""Post-FT aggregation jobs — rebuild PlayerTournamentStats and TeamSeasonStats from
the persistent archive. Zero API cost; runs on a slow schedule after matches finish.

The live poller and prefetch job feed the archive (MatchEvent, MatchStatistics, etc.).
These rebuilders turn that raw archive into the queryable aggregates used by the
golden-boot UI, model improvements, and the /wcdata public API.
"""
from __future__ import annotations

import logging

from backend.data.persistence import (
    rebuild_player_tournament_stats,
    rebuild_team_season_stats,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)


async def rebuild_aggregations() -> dict:
    """Recompute PlayerTournamentStats + TeamSeasonStats from the archive."""
    db = SessionLocal()
    try:
        players = rebuild_player_tournament_stats(db)
        teams = rebuild_team_season_stats(db)
        db.commit()
        return {"players": players, "teams": teams}
    except Exception as exc:
        logger.warning("aggregation rebuild failed: %s", exc)
        db.rollback()
        return {"players": 0, "teams": 0, "error": str(exc)}
    finally:
        db.close()
