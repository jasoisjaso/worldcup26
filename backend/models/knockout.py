"""Extra-time & penalty resolution for knockout ties.

The Dixon-Coles score grid gives the regulation (90') distribution. In a
knockout a tie that's level after 90' plays 30' of extra time, and if still
level, penalties. This turns the regulation lambdas into a full "how is the tie
decided?" breakdown — P(decided in 90'), P(extra time), P(penalties) — plus each
side's overall probability of ADVANCING (regulation + ET + shootout combined).

Extra time is modelled as a fresh 30' mini-match with each side's scoring rate
scaled to a third of a match and damped by ET_CAUTION (extra time is a touch
lower-scoring than open play — fatigue + risk-aversion; both sides would rather
take their chance from 12 yards than concede). Penalties are a near coin-flip
with only a small edge to the side the model rates higher over the run of play —
enough to reflect the weak "better side tends to hold its nerve" signal without
pretending a shootout is predictable.
"""
from __future__ import annotations

from backend.models.poisson import build_score_matrix

ET_FRACTION = 30.0 / 90.0     # extra time is a third of a match
ET_CAUTION = 0.90             # ET is a touch lower-scoring per minute than regulation
PEN_FAVOURITE_EDGE = 0.04     # ±4% off a coin-flip toward the run-of-play favourite


def _split(grid) -> tuple[float, float, float]:
    """(P(home ahead), P(level), P(away ahead)) from a score-probability grid."""
    ph = pd = pa = 0.0
    for h in range(len(grid)):
        row = grid[h]
        for a in range(len(row)):
            p = row[a]
            if h > a:
                ph += p
            elif a > h:
                pa += p
            else:
                pd += p
    return ph, pd, pa


def knockout_resolution(lambda_home: float, lambda_away: float) -> dict:
    """Full ET/penalty breakdown from the regulation scoring rates.

    Returns probabilities (0-1) for how the tie is decided plus each side's
    overall chance of going through.
    """
    reg = build_score_matrix(lambda_home, lambda_away, max_goals=10)
    p_home_90, p_draw_90, p_away_90 = _split(reg)

    et = build_score_matrix(
        lambda_home * ET_FRACTION * ET_CAUTION,
        lambda_away * ET_FRACTION * ET_CAUTION,
        max_goals=6,
    )
    p_home_et, p_draw_et, p_away_et = _split(et)

    # Penalties: near coin-flip, small edge to the run-of-play favourite.
    if p_home_90 >= p_away_90:
        pen_home, pen_away = 0.5 + PEN_FAVOURITE_EDGE, 0.5 - PEN_FAVOURITE_EDGE
    else:
        pen_home, pen_away = 0.5 - PEN_FAVOURITE_EDGE, 0.5 + PEN_FAVOURITE_EDGE

    p_decided_90 = p_home_90 + p_away_90
    p_extra_time = p_draw_90                     # any tie level after 90'
    p_penalties = p_draw_90 * p_draw_et          # still level after ET
    p_decided_et = p_draw_90 * (p_home_et + p_away_et)

    p_home_adv = p_home_90 + p_draw_90 * (p_home_et + p_draw_et * pen_home)
    p_away_adv = p_away_90 + p_draw_90 * (p_away_et + p_draw_et * pen_away)
    total = p_home_adv + p_away_adv              # ~1.0; renormalise float drift
    if total > 0:
        p_home_adv /= total
        p_away_adv /= total

    # float() casts numpy scalars (build_score_matrix is numpy-backed) so the
    # payload serialises cleanly to JSON.
    return {
        "decided_in_90": round(float(p_decided_90), 4),
        "extra_time": round(float(p_extra_time), 4),       # reaches ET
        "penalties": round(float(p_penalties), 4),         # reaches a shootout
        "decided_in_et": round(float(p_decided_et), 4),    # settled during ET
        "home_advance": round(float(p_home_adv), 4),
        "away_advance": round(float(p_away_adv), 4),
        "reg_home": round(float(p_home_90), 4),
        "reg_draw": round(float(p_draw_90), 4),
        "reg_away": round(float(p_away_90), 4),
    }
