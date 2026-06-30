"""Public endpoints for model-picked multi bets + their settled track record."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.models import Match, ModelMulti, ModelMultiLeg, Team
from backend.db.session import get_db
from backend.util.datetime import iso_utc

router = APIRouter()


def _serialize_multi(db: Session, mm: ModelMulti) -> dict:
    legs = db.query(ModelMultiLeg).filter(ModelMultiLeg.multi_id == mm.id).order_by(ModelMultiLeg.leg_order.asc()).all()
    leg_out = []
    for leg in legs:
        m = db.get(Match, leg.match_id)
        home = db.query(Team).filter(Team.code == m.home_code).first() if m else None
        away = db.query(Team).filter(Team.code == m.away_code).first() if m else None
        leg_out.append({
            "leg_order": leg.leg_order,
            "match_id": leg.match_id,
            "match_label": f"{home.name} v {away.name}" if home and away else leg.match_id,
            "kickoff_iso": iso_utc(m.kickoff) if m else None,
            "market": leg.market,
            "market_label": leg.market_label,
            "model_prob": leg.model_prob,
            "market_implied_prob": leg.market_implied_prob,
            "book_odds": leg.book_odds,
            "book_name": leg.book_name,
            "status": leg.leg_status,
            "actual_score": (
                f"{m.home_score}-{m.away_score}" if m and m.home_score is not None and m.away_score is not None
                else None
            ),
        })
    return {
        "id": mm.id,
        "generated_at": mm.generated_at.isoformat() if mm.generated_at else None,
        "label": mm.label,
        "kind": mm.kind,
        "combined_prob": mm.combined_prob,
        "combined_fair_odds": mm.combined_fair_odds,
        "combined_book_odds": mm.combined_book_odds,
        "ev_pct": mm.ev_pct,
        "kelly_pct": mm.kelly_pct,
        "status": mm.status,
        "settled_at": mm.settled_at.isoformat() if mm.settled_at else None,
        "profit_loss_units": mm.profit_loss_units,
        "legs": leg_out,
    }


@router.get("/model-multis")
async def list_model_multis(db: Session = Depends(get_db)):
    """Active model-picked multis + recent settled history + running ROI."""
    # Active = pending and at least one leg still pre-kickoff
    pending = (
        db.query(ModelMulti)
        .filter(ModelMulti.status == "pending")
        .order_by(ModelMulti.generated_at.desc())
        .all()
    )
    # Recent = last 20 settled
    recent = (
        db.query(ModelMulti)
        .filter(ModelMulti.status.in_(["won", "lost", "void"]))
        .order_by(ModelMulti.settled_at.desc())
        .limit(20)
        .all()
    )

    # Stats
    all_settled = db.query(ModelMulti).filter(ModelMulti.status.in_(["won", "lost"])).all()
    total_settled = len(all_settled)
    won = sum(1 for x in all_settled if x.status == "won")
    pnl = sum((x.profit_loss_units or 0) for x in all_settled)
    roi = (pnl / total_settled * 100) if total_settled else None

    return {
        "active": [_serialize_multi(db, m) for m in pending],
        "recent": [_serialize_multi(db, m) for m in recent],
        "stats": {
            "total_settled": total_settled,
            "won": won,
            "lost": total_settled - won,
            "hit_rate_pct": round((won / total_settled * 100), 1) if total_settled else None,
            "profit_loss_units": round(pnl, 2),
            "roi_pct": round(roi, 1) if roi is not None else None,
        },
    }
