"""Public read-only endpoints that surface the model's learning signals
and the persistent injury layer."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.data.calibration_logger import rolling_calibration
from backend.data.fetchers.injuries_persist import get_injury_flags_for_match
from backend.db.models import Match
from backend.db.session import get_db

router = APIRouter()


@router.get("/calibration")
async def get_calibration():
    """Rolling Brier + log loss + hit rate over the last 10 settled matches
    vs all-time. The delta is the 'is the model getting sharper?' signal."""
    return rolling_calibration(window=10)


@router.get("/match/{match_id}/injury-flags")
async def match_injury_flags(match_id: str, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        return {"error": "unknown_match"}
    return get_injury_flags_for_match(m.home_code, m.away_code)
