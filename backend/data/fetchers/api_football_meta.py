"""api-football's own /predictions endpoint as a meta-signal.

For every match we harvest, api-football's API publishes their own model's
1X2 probabilities (pct_home / pct_draw / pct_away) plus comparison metrics
(form/attack/defence ratings 0-100). We persist these into the
`api_football_predictions` table via harvest_processor but the prediction
pipeline currently doesn't read them.

Use cases for the meta-signal
-----------------------------
1. AGREEMENT SCORE: when our blended 1X2 and api-football's 1X2 land on the
   same modal outcome AND the bookmaker disagrees, the value claim is
   stronger than either model alone. Surfaced as a per-match field; the FE
   can render a "two-model consensus" badge on value picks.
2. CONFIDENCE DAMPENING: when api-football wildly disagrees with us on a
   match, we can dial down the confidence label without changing our prob
   estimate (just one fewer "high confidence" pill).

NOT a lambda modifier
---------------------
Ensembling another model into ours via lambda is doable but high-risk
without offline backtests — different model architectures, unknown
correlation. For now we EXPOSE the meta-signal in the prediction response
so the FE can use it; ensembling is a Phase-2.b decision.
"""
from __future__ import annotations

from backend.db.session import SessionLocal
from backend.db.models import ApiFootballPrediction


def _parse_pct(raw) -> float | None:
    """api-football stores percentages as strings like '67%'. Return 0..100 float
    (NOT 0..1 — caller normalises). Returns None for missing/malformed input."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    s = str(raw).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1].strip()
    try:
        return float(s)
    except ValueError:
        return None


def get_api_football_prediction(match_id: str) -> dict | None:
    """Return the api-football model's view for `match_id`, or None when we
    have no harvested prediction for it yet.

    Shape:
        {
            "home_win": float (0..1),
            "draw": float,
            "away_win": float,
            "winner_name": str | None,
            "advice": str | None,
            "comparison": {
                "form": (home_pct, away_pct),     # 0-100
                "att":  (home_pct, away_pct),
                "def":  (home_pct, away_pct),
            },
        }
    """
    db = SessionLocal()
    try:
        row = (
            db.query(ApiFootballPrediction)
            .filter(ApiFootballPrediction.match_id == match_id)
            .order_by(ApiFootballPrediction.id.desc())
            .first()
        )
        if not row:
            return None
        # api-football publishes percentages as strings like '67%' — parse to
        # float, then normalise to 0..1.
        ph_raw = _parse_pct(row.pct_home)
        pd_raw = _parse_pct(row.pct_draw)
        pa_raw = _parse_pct(row.pct_away)
        if ph_raw is None or pd_raw is None or pa_raw is None:
            return None
        ph, pd, pa = ph_raw / 100.0, pd_raw / 100.0, pa_raw / 100.0
        # Defensive renormalise — if all three are zero, bail; if they sum to
        # something other than ~1.0 (rounding artefacts), pro-rate.
        total = ph + pd + pa
        if total <= 0:
            return None
        if abs(total - 1.0) > 1e-3:
            ph, pd, pa = ph / total, pd / total, pa / total

        def _pair(h_raw, a_raw) -> tuple[float, float] | None:
            h = _parse_pct(h_raw)
            a = _parse_pct(a_raw)
            if h is None and a is None:
                return None
            return ((h or 0) / 100.0, (a or 0) / 100.0)

        return {
            "home_win": round(ph, 4),
            "draw": round(pd, 4),
            "away_win": round(pa, 4),
            "winner_name": row.winner_name,
            "advice": row.advice,
            "comparison": {
                "form": _pair(row.comp_form_home, row.comp_form_away),
                "att": _pair(row.comp_att_home, row.comp_att_away),
                "def": _pair(row.comp_def_home, row.comp_def_away),
            },
        }
    finally:
        db.close()


def agreement_with(our_probs: dict, their_probs: dict) -> dict:
    """Agreement signal between our blended 1X2 and api-football's 1X2.

    Returns a small dict that's safe to attach to the public prediction
    response:
        {
            "modal_match": bool,           # both pick the same outcome
            "kl_divergence": float,        # 0..~2 — lower = closer agreement
            "label": "consensus" | "moderate" | "diverging",
        }
    """
    import math
    pairs = [
        ("home_win", our_probs.get("home_win", 0), their_probs.get("home_win", 0)),
        ("draw",     our_probs.get("draw", 0),     their_probs.get("draw", 0)),
        ("away_win", our_probs.get("away_win", 0), their_probs.get("away_win", 0)),
    ]
    our_modal = max(pairs, key=lambda x: x[1])[0]
    their_modal = max(pairs, key=lambda x: x[2])[0]
    # KL(our || their) — penalises disagreement on highest-prob outcomes more.
    kl = 0.0
    for _, p, q in pairs:
        if p > 1e-6 and q > 1e-6:
            kl += p * math.log(p / q)
    if our_modal == their_modal and kl < 0.05:
        label = "consensus"
    elif kl < 0.20:
        label = "moderate"
    else:
        label = "diverging"
    return {
        "modal_match": our_modal == their_modal,
        "kl_divergence": round(kl, 4),
        "label": label,
    }
