"""Tournament-wide model projections: per-team group-finish and advancement
probabilities from a Monte-Carlo simulation of the remaining fixtures."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.data.tournament_cache import get_tournament

router = APIRouter()


@router.get("/projections")
async def projections(db: Session = Depends(get_db)):
    return await get_tournament(db)
