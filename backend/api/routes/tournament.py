"""Tournament-wide model projections: per-team group-finish and advancement
probabilities from a Monte-Carlo simulation of the remaining fixtures."""
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.models import LiveMatchState, Match
from backend.db.session import get_db
from backend.data.tournament_cache import get_tournament
from backend.util.datetime import iso_utc

router = APIRouter()


@router.get("/projections")
async def projections(db: Session = Depends(get_db)):
    return await get_tournament(db)


@router.get("/progress")
async def progress(db: Session = Depends(get_db)):
    """Group-stage progress for the header strip. 72 group games total; we
    count completed/in-play and surface the next kickoff so users can see at a
    glance how far the tournament is."""
    matches = db.query(Match).all()
    group_matches = [m for m in matches if m.matchday in (1, 2, 3)]
    total = len(group_matches) or 72
    complete = sum(1 for m in group_matches if m.status == "complete")

    in_play_ids = {
        s.match_id for s in db.query(LiveMatchState.match_id)
        .filter(LiveMatchState.status.in_(["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]))
        .all()
    }
    in_play = sum(1 for m in group_matches if m.id in in_play_ids)

    now = datetime.utcnow()
    next_match = (
        db.query(Match)
        .filter(Match.matchday.in_([1, 2, 3]))
        .filter(Match.status != "complete")
        .filter(Match.kickoff > now - timedelta(minutes=5))
        .order_by(Match.kickoff.asc())
        .first()
    )

    return {
        "stage": "group",
        "total": total,
        "complete": complete,
        "in_play": in_play,
        "remaining": total - complete - in_play,
        "next_kickoff_iso": iso_utc(next_match.kickoff) if next_match else None,
    }
