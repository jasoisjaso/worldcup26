"""Extra fan-engagement endpoints from api-football pro tier."""
from fastapi import APIRouter, HTTPException
from sqlalchemy.orm import Session
from fastapi import Depends

from backend.db.session import get_db
from backend.db.models import Match
from backend.data.fetchers.topscorers import get_topscorers, refresh_topscorers
from backend.data.fetchers.h2h import get_h2h

router = APIRouter()


@router.get("/topscorers")
async def topscorers():
    """Golden Boot Watch — WC2026 leading scorers. Refreshed hourly server-side."""
    return get_topscorers()


@router.post("/topscorers/refresh")
async def topscorers_refresh():
    """Force a topscorer refresh. The scheduler runs this hourly; this is for dev/verification."""
    await refresh_topscorers()
    return get_topscorers()


@router.get("/matches/{match_id}/h2h")
async def match_h2h(match_id: str, db: Session = Depends(get_db)):
    """Head-to-head record between this match's home and away. Cached 6h server-side."""
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    out = await get_h2h(m.home_code, m.away_code, last_n=10)
    if out is None:
        return {"home_code": m.home_code, "away_code": m.away_code, "matches": [], "total_meetings": 0, "our_wins": 0, "opp_wins": 0, "draws": 0}
    return out
