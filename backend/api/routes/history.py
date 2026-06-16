from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Prediction, Match, Team, PredictionSnapshot
from backend.eval.scoring import (
    outcome_index, ordinal_rps, log_loss, brier,
    binary_brier, binary_log_loss, reliability_table, expected_calibration_error,
)

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
        "closing_odds": pred.closing_odds,
        "clv": pred.clv,
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
            settled.append((c, p.bookmaker_odds or 1.0, p.ev or 0.0, p.our_probability))

    if not settled:
        avg_ev = sum(p.ev or 0 for p in preds) / total
        return {"accuracy": 0, "avg_ev": round(avg_ev, 4), "roi": 0, "total": total, "correct": 0}

    correct = sum(1 for c, _, _, _ in settled if c)
    accuracy = correct / len(settled)
    avg_ev = sum(ev for _, _, ev, _ in settled) / len(settled)
    # ROI: sum of (odds - 1) for wins minus losses, divided by total staked
    roi = sum((odds - 1) if c else -1 for c, odds, _, _ in settled) / len(settled)

    # Proper scoring on the binary pick outcome — a 99% and a 51% correct call differ.
    # These are conditioned on the +EV pick selection; /history/calibration is unbiased.
    pairs = [(prob, c) for c, _, _, prob in settled]
    brier_bin = sum(binary_brier(p, c) for p, c in pairs) / len(pairs)
    ll_bin = sum(binary_log_loss(p, c) for p, c in pairs) / len(pairs)

    # Closing Line Value — the sharpest read on whether the edge is real. Scored over every
    # pick that has a captured, de-viggable closing line (not just settled ones).
    clv_vals = [p.clv for p in preds if p.clv is not None]
    clv_block = {}
    if clv_vals:
        clv_block = {
            "clv_n": len(clv_vals),
            "avg_clv": round(sum(clv_vals) / len(clv_vals), 4),
            "clv_beat_close_rate": round(sum(1 for v in clv_vals if v > 0) / len(clv_vals), 4),
        }

    return {
        "accuracy": round(accuracy, 4),
        "avg_ev": round(avg_ev, 4),
        "roi": round(roi, 4),
        "total": total,
        "correct": correct,
        "brier": round(brier_bin, 4),
        "log_loss": round(ll_bin, 4),
        "ece": expected_calibration_error(pairs),
        **clv_block,
        "note": "brier/log_loss/ece are conditioned on +EV pick selection; see /history/calibration for unbiased scores. CLV is the sharpest edge signal once enough picks settle.",
    }


@router.get("/calibration")
def get_calibration(db: Session = Depends(get_db)):
    """Unbiased proper-scoring of the model over every snapshotted match that has finished.

    Uses PredictionSnapshot (logged for ALL upcoming matches, not just +EV picks), so RPS /
    Brier / log-loss / reliability reflect the deployed model's true calibration."""
    snaps = db.query(PredictionSnapshot).all()
    rps_v = ll_v = brier_v = 0.0
    n = 0
    win_pairs: list[tuple[float, bool]] = []
    over_pairs: list[tuple[float, bool]] = []
    btts_pairs: list[tuple[float, bool]] = []
    by_version: dict[str, dict] = {}
    for s in snaps:
        m = db.get(Match, s.match_id)
        if not m or m.status != "complete" or m.home_score is None or m.away_score is None:
            continue
        if s.p_home is None:
            continue
        obs = outcome_index(m.home_score, m.away_score)
        probs = (s.p_home, s.p_draw, s.p_away)
        r = ordinal_rps(probs, obs)
        ll = log_loss(probs, obs)
        b = brier(probs, obs)
        rps_v += r
        ll_v += ll
        brier_v += b
        n += 1
        pred_i = max(range(3), key=lambda i: probs[i])
        win_pairs.append((probs[pred_i], pred_i == obs))
        if s.p_over_2_5 is not None:
            over_pairs.append((s.p_over_2_5, (m.home_score + m.away_score) > 2))
        if s.p_btts is not None:
            btts_pairs.append((s.p_btts, m.home_score > 0 and m.away_score > 0))
        v = by_version.setdefault(s.model_version or "unknown", {"rps": 0.0, "n": 0})
        v["rps"] += r
        v["n"] += 1

    if n == 0:
        return {"n": 0, "note": "no completed snapshotted matches yet"}

    def _binary_block(pairs: list[tuple[float, bool]]) -> dict | None:
        if not pairs:
            return None
        return {
            "n": len(pairs),
            "brier": round(sum(binary_brier(p, o) for p, o in pairs) / len(pairs), 4),
            "log_loss": round(sum(binary_log_loss(p, o) for p, o in pairs) / len(pairs), 4),
            "ece": expected_calibration_error(pairs),
            "reliability": reliability_table(pairs),
        }

    # Per-market segmentation: aggregate calibration can hide a market that is badly
    # miscalibrated (the fixed-sum ELO->lambda total can skew totals/BTTS while 1X2 looks
    # fine), and value bets concentrate exactly where calibration is weakest.
    by_market = {
        "result_1x2": {
            "n": n,
            "rps": round(rps_v / n, 4),
            "log_loss": round(ll_v / n, 4),
            "brier": round(brier_v / n, 4),
            "ece": expected_calibration_error(win_pairs),
            "reliability": reliability_table(win_pairs),
        },
        "over_under_2_5": _binary_block(over_pairs),
        "btts": _binary_block(btts_pairs),
    }

    return {
        "n": n,
        "rps": round(rps_v / n, 4),
        "log_loss": round(ll_v / n, 4),
        "brier": round(brier_v / n, 4),
        "ece_winner": expected_calibration_error(win_pairs),
        "reliability_winner": reliability_table(win_pairs),
        "over_2_5_brier": round(sum(binary_brier(p, o) for p, o in over_pairs) / len(over_pairs), 4) if over_pairs else None,
        "by_market": by_market,
        "by_model_version": {k: {"rps": round(v["rps"] / v["n"], 4), "n": v["n"]} for k, v in by_version.items()},
    }
