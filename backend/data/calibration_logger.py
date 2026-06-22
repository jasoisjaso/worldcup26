"""Per-match calibration tracker.

Once a match completes, compute Brier + log-loss + favourite-correctness on
the model's pre-kickoff probabilities (from PredictionSnapshot) versus the
actual result. Write to ModelCalibrationLog. Drives the rolling-accuracy
display on /performance — the model getting sharper (or not) as the
tournament progresses is the most concrete proof of learning.
"""
from __future__ import annotations

import logging
import math
from datetime import datetime

from backend.db.models import Match, ModelCalibrationLog, PredictionSnapshot
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)


def _result_vec(home: int, away: int) -> tuple[float, float, float]:
    if home > away:
        return 1.0, 0.0, 0.0
    if home < away:
        return 0.0, 0.0, 1.0
    return 0.0, 1.0, 0.0


# --- confidence-band reliability -------------------------------------------
# Buckets settled predictions by the model's TOP probability and reports the
# realised hit-rate per band. Powers the "when we said ~60%, it happened X% of
# the time (n=Z)" badge on the match page + report card — an honest, sample-aware
# reliability read straight from our own track record.

_BANDS = ("<40%", "40-50%", "50-60%", "60-70%", "70-85%", "85%+")


def _band_for(top_prob: float) -> str:
    if top_prob < 0.40:
        return "<40%"
    if top_prob < 0.50:
        return "40-50%"
    if top_prob < 0.60:
        return "50-60%"
    if top_prob < 0.70:
        return "60-70%"
    if top_prob < 0.85:
        return "70-85%"
    return "85%+"


def confidence_bands_from_rows(rows: list[tuple[float, int]]) -> list[dict]:
    """Aggregate (top_prob, favourite_correct) pairs into per-band reliability.

    Returns one dict per band that actually has data, in fixed band order:
      {band, n, hit_rate, expected}  where expected = mean predicted top-prob
      in the band (so the FE can show predicted-vs-realised side by side).
    """
    buckets: dict[str, list[tuple[float, int]]] = {}
    for top_prob, correct in rows:
        buckets.setdefault(_band_for(top_prob), []).append((top_prob, correct))
    out: list[dict] = []
    for band in _BANDS:
        items = buckets.get(band)
        if not items:
            continue
        n = len(items)
        hit_rate = sum(c for _, c in items) / n
        expected = sum(p for p, _ in items) / n
        out.append({
            "band": band,
            "n": n,
            "hit_rate": round(hit_rate, 3),
            "expected": round(expected, 3),
        })
    return out


def confidence_band_record() -> dict:
    """Reliability by confidence band over every settled match (from the
    calibration log). Honest + unbiased — uses the pre-kickoff snapshot for
    EVERY match, not just the value picks."""
    db = SessionLocal()
    try:
        rows = db.query(ModelCalibrationLog).all()
        pairs: list[tuple[float, int]] = []
        for r in rows:
            probs = [
                getattr(r, "pre_p_home", None) or 0.0,
                getattr(r, "pre_p_draw", None) or 0.0,
                getattr(r, "pre_p_away", None) or 0.0,
            ]
            top = max(probs)
            if top <= 0:
                continue
            pairs.append((top, int(r.favorite_correct or 0)))
        return {"total": len(pairs), "bands": confidence_bands_from_rows(pairs)}
    finally:
        db.close()


def log_finished_matches() -> dict:
    """Compute calibration entries for any completed match that doesn't have
    one yet. Idempotent — uses unique constraint on match_id.

    Interruption gate: only enrol matches with interruption_status NULL.
    A match marked 'awarded' (3-0 walkover) is excluded too — the official
    score wasn't earned on the pitch, so scoring the model against it would
    contaminate the calibration trend. See
    docs/plans/2026-06-23_match-interruption-handling.md §7b.
    """
    db = SessionLocal()
    try:
        complete = (
            db.query(Match)
            .filter(Match.status == "complete")
            .filter(Match.interruption_status.is_(None))
            .filter(Match.home_score.isnot(None))
            .filter(Match.away_score.isnot(None))
            .all()
        )
        added = 0
        for m in complete:
            existing = db.query(ModelCalibrationLog).filter(ModelCalibrationLog.match_id == m.id).first()
            if existing:
                continue
            snap = db.query(PredictionSnapshot).filter(PredictionSnapshot.match_id == m.id).first()
            if not snap:
                continue
            # PredictionSnapshot stores p_home/p_draw/p_away
            ph = getattr(snap, "p_home", None)
            pd = getattr(snap, "p_draw", None)
            pa = getattr(snap, "p_away", None)
            if ph is None or pd is None or pa is None:
                continue
            yh, yd, ya = _result_vec(m.home_score, m.away_score)
            # 1X2 Brier = mean squared error across the three outcomes
            brier = ((ph - yh) ** 2 + (pd - yd) ** 2 + (pa - ya) ** 2) / 3.0
            # Log loss on the realised outcome only
            p_realised = ph if yh else pd if yd else pa
            log_loss = -math.log(max(p_realised, 1e-9))
            # Favourite-correct: did our highest pre-kickoff prob win?
            best = max(("home", ph), ("draw", pd), ("away", pa), key=lambda x: x[1])[0]
            won = (best == "home" and yh) or (best == "draw" and yd) or (best == "away" and ya)
            db.add(ModelCalibrationLog(
                match_id=m.id,
                settled_at=datetime.utcnow(),
                home_score=m.home_score,
                away_score=m.away_score,
                pre_p_home=ph,
                pre_p_draw=pd,
                pre_p_away=pa,
                brier_1x2=round(brier, 6),
                log_loss_1x2=round(log_loss, 6),
                favorite_correct=1 if won else 0,
            ))
            added += 1
        db.commit()
        return {"added": added, "total_complete": len(complete)}
    finally:
        db.close()


def rolling_calibration(window: int = 10) -> dict:
    """Last-N Brier vs all-time Brier. The delta tells you whether the model
    is sharpening as the tournament goes (negative = better; positive = worse)."""
    db = SessionLocal()
    try:
        all_rows = (
            db.query(ModelCalibrationLog)
            .order_by(ModelCalibrationLog.settled_at.asc())
            .all()
        )
        if not all_rows:
            return {"total": 0}
        recent = all_rows[-window:]
        def avg(rows, attr):
            vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
            return sum(vals) / len(vals) if vals else None
        return {
            "total": len(all_rows),
            "all_time_brier": round(avg(all_rows, "brier_1x2") or 0, 4),
            "all_time_log_loss": round(avg(all_rows, "log_loss_1x2") or 0, 4),
            "all_time_hit_rate": round(sum(r.favorite_correct or 0 for r in all_rows) / len(all_rows), 4),
            "recent_brier": round(avg(recent, "brier_1x2") or 0, 4),
            "recent_log_loss": round(avg(recent, "log_loss_1x2") or 0, 4),
            "recent_hit_rate": round(sum(r.favorite_correct or 0 for r in recent) / len(recent), 4),
            "window": window,
            "trend_brier": round((avg(recent, "brier_1x2") or 0) - (avg(all_rows, "brier_1x2") or 0), 4),
        }
    finally:
        db.close()
