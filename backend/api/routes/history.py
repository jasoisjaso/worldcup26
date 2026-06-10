from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Prediction, Match, Team

router = APIRouter()


def _pick_label(market: str, home: "Team | None", away: "Team | None") -> str:
    if market == "home_win":
        return f"{home.name} Win" if home else "Home Win"
    if market == "away_win":
        return f"{away.name} Win" if away else "Away Win"
    if market == "draw":
        return "Draw"
    if market == "over_2_5":
        return "Over 2.5 Goals"
    if market == "btts":
        return "Both Teams Score"
    return market.replace("_", " ").title()


def _entry_dict(pred: Prediction, match: Match | None, home: Team | None, away: Team | None) -> dict:
    match_label = f"{home.name} vs {away.name}" if home and away else pred.match_id
    home_code = match.home_code if match else ""
    away_code = match.away_code if match else ""
    home_flag = home.flag_url if home else ""
    away_flag = away.flag_url if away else ""
    return {
        "id": pred.id,
        "match_id": pred.match_id,
        "match_label": match_label,
        "home_code": home_code,
        "away_code": away_code,
        "home_name": home.name if home else "",
        "away_name": away.name if away else "",
        "home_flag_url": home_flag,
        "away_flag_url": away_flag,
        "market": pred.market,
        "market_label": pred.market.replace("_", " ").title(),
        "pick_label": _pick_label(pred.market, home, away),
        "our_probability": pred.our_probability,
        "bookmaker_odds": pred.bookmaker_odds,
        "ev": pred.ev,
        "logged_at": pred.logged_at.isoformat() if pred.logged_at else None,
        "actual_result": _settle_result(pred, match),
        "correct": _is_correct(pred, match),
    }


def _settle_result(pred: Prediction, match: Match | None) -> str | None:
    if not match or match.status != "complete":
        return None
    if match.home_score is None or match.away_score is None:
        return None
    hs, as_ = match.home_score, match.away_score
    if pred.market == "home_win":
        return "win" if hs > as_ else "loss"
    if pred.market == "draw":
        return "win" if hs == as_ else "loss"
    if pred.market == "away_win":
        return "win" if as_ > hs else "loss"
    if pred.market == "over_2_5":
        return "win" if (hs + as_) > 2 else "loss"
    if pred.market == "btts":
        return "win" if (hs > 0 and as_ > 0) else "loss"
    return None


def _is_correct(pred: Prediction, match: Match | None) -> bool | None:
    result = _settle_result(pred, match)
    if result is None:
        return None
    return result == "win"


@router.get("")
def get_history(db: Session = Depends(get_db)):
    preds = db.query(Prediction).order_by(Prediction.logged_at.desc()).all()
    result = []
    for p in preds:
        match = db.get(Match, p.match_id)
        home = db.get(Team, match.home_code) if match else None
        away = db.get(Team, match.away_code) if match else None
        result.append(_entry_dict(p, match, home, away))
    return result


@router.get("/stats")
def get_stats(db: Session = Depends(get_db)):
    preds = db.query(Prediction).all()
    if not preds:
        return {"accuracy": 0, "avg_ev": 0, "roi": 0, "total": 0, "correct": 0}

    total = len(preds)
    settled = []
    for p in preds:
        match = db.get(Match, p.match_id)
        c = _is_correct(p, match)
        if c is not None:
            settled.append((c, p.bookmaker_odds or 1.0, p.ev or 0.0))

    if not settled:
        avg_ev = sum(p.ev or 0 for p in preds) / total
        return {"accuracy": 0, "avg_ev": round(avg_ev, 4), "roi": 0, "total": total, "correct": 0}

    correct = sum(1 for c, _, _ in settled if c)
    accuracy = correct / len(settled)
    avg_ev = sum(ev for _, _, ev in settled) / len(settled)
    # ROI: sum of (odds - 1) for wins minus losses, divided by total staked
    roi = sum((odds - 1) if c else -1 for c, odds, _ in settled) / len(settled)
    return {
        "accuracy": round(accuracy, 4),
        "avg_ev": round(avg_ev, 4),
        "roi": round(roi, 4),
        "total": total,
        "correct": correct,
    }
