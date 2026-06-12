"""Proper scoring rules shared by the offline backtest and the online /stats tracker.

These reward calibrated, discriminating probabilities — unlike raw win/loss accuracy,
which gives a 51% and a 99% correct call identical credit.
"""
from __future__ import annotations

import math

Probs3 = "tuple[float, float, float]"  # [home, draw, away]


def outcome_index(home_goals: int, away_goals: int) -> int:
    """0 = home win, 1 = draw, 2 = away win."""
    return 0 if home_goals > away_goals else (1 if home_goals == away_goals else 2)


def ordinal_rps(probs, obs: int) -> float:
    """Ranked Probability Score for ordered 1X2 outcomes. Lower is better.

    RPS = 1/(r-1) * Σ (cumulative_pred − cumulative_obs)²  over r-1 categories (r=3).
    """
    cp1 = probs[0]
    cp2 = probs[0] + probs[1]
    o1 = 1.0 if obs == 0 else 0.0
    o2 = 1.0 if obs in (0, 1) else 0.0
    return 0.5 * ((cp1 - o1) ** 2 + (cp2 - o2) ** 2)


def log_loss(probs, obs: int) -> float:
    return -math.log(max(1e-12, probs[obs]))


def brier(probs, obs: int) -> float:
    return sum((probs[i] - (1.0 if i == obs else 0.0)) ** 2 for i in range(3))


def binary_brier(p: float, happened: bool) -> float:
    return (p - (1.0 if happened else 0.0)) ** 2


def binary_log_loss(p: float, happened: bool) -> float:
    p = min(1 - 1e-12, max(1e-12, p))
    return -(math.log(p) if happened else math.log(1.0 - p))


def reliability_table(pairs: list[tuple[float, bool]], bins: int = 10) -> list[dict]:
    """Group (predicted_prob, happened) into bins; return per-bin confidence vs frequency."""
    acc = [{"conf_sum": 0.0, "hits": 0, "n": 0} for _ in range(bins)]
    for p, happened in pairs:
        b = min(bins - 1, int(p * bins))
        acc[b]["conf_sum"] += p
        acc[b]["hits"] += 1 if happened else 0
        acc[b]["n"] += 1
    out = []
    for b in range(bins):
        n = acc[b]["n"]
        if n == 0:
            continue
        out.append({
            "bucket": f"{b / bins:.1f}-{(b + 1) / bins:.1f}",
            "confidence": round(acc[b]["conf_sum"] / n, 4),
            "frequency": round(acc[b]["hits"] / n, 4),
            "n": n,
        })
    return out


def expected_calibration_error(pairs: list[tuple[float, bool]], bins: int = 10) -> float:
    n_total = len(pairs)
    if n_total == 0:
        return 0.0
    table = reliability_table(pairs, bins)
    return round(sum((row["n"] / n_total) * abs(row["confidence"] - row["frequency"]) for row in table), 4)
