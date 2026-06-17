"""Same-game multi (correlated within-match) pricing.

The right way to price a multi whose legs are all functions of the final score is to read
the joint probability straight off the Dixon-Coles score grid we already build: sum the
cells that satisfy every leg at once. That captures the true correlation exactly (a
favourite winning is positively correlated with Over but negatively with both-teams-score),
with no copula and no tuning. ``joint_probability_from_grid`` does that.

``sgm_probability`` (the older hand-tuned-multiplier heuristic) is kept only as a fallback
for callers that do not have the grid to hand.
"""
import numpy as np


# --- Exact joint probability from the score grid (preferred) ---------------------------

def _line(market: str) -> float:
    # "over_2_5" -> 2.5 ; "home_over_1_5" -> 1.5
    a, b = market.rsplit("_", 2)[-2:]
    return float(f"{a}.{b}")


def _leg_mask(market: str, I: np.ndarray, J: np.ndarray):
    """Boolean grid (home goals I, away goals J) of scorelines that satisfy one leg.

    Returns None for a market that is not a pure function of the final score (e.g. a
    half-time leg), so the caller can fall back rather than price it wrong.
    """
    if market in ("home_win", "home"):
        return I > J
    if market == "draw":
        return I == J
    if market in ("away_win", "away"):
        return I < J
    if market in ("double_chance_1x", "1x"):
        return I >= J
    if market in ("double_chance_x2", "x2"):
        return I <= J
    if market in ("double_chance_12", "12"):
        return I != J
    if market in ("btts", "btts_yes"):
        return (I >= 1) & (J >= 1)
    if market == "btts_no":
        return (I == 0) | (J == 0)
    if market in ("home_cs", "home_clean_sheet"):  # home clean sheet -> away scores 0
        return J == 0
    if market in ("away_cs", "away_clean_sheet"):
        return I == 0
    if market.startswith("over_"):
        return (I + J) > _line(market)
    if market.startswith("under_"):
        return (I + J) < _line(market)
    if market.startswith("home_over_"):
        return I > _line(market)
    if market.startswith("home_under_"):
        return I < _line(market)
    if market.startswith("away_over_"):
        return J > _line(market)
    if market.startswith("away_under_"):
        return J < _line(market)
    if market == "ah_home_minus1":      # home wins by 2+
        return (I - J) >= 2
    if market == "ah_home_plus1":       # home covers unless it loses by 2+
        return (I - J) >= 0
    if market == "ah_away_minus1":
        return (J - I) >= 2
    if market == "ah_away_plus1":
        return (J - I) >= 0
    return None


def joint_probability_from_grid(matrix: np.ndarray, markets: list[str]) -> float | None:
    """Exact P(all legs) by summing the score-grid cells that satisfy every leg.

    Returns None if any leg is not a pure function of the final score, so the caller can
    fall back to the heuristic instead of silently mispricing.
    """
    if not markets:
        return 0.0
    rows, cols = matrix.shape
    I, J = np.indices((rows, cols))
    mask = np.ones((rows, cols), dtype=bool)
    for m in markets:
        lm = _leg_mask(m, I, J)
        if lm is None:
            return None
        mask &= lm
    return float(matrix[mask].sum())


# --- Hand-tuned heuristic (fallback only when no grid is available) ---------------------

SGM_CORRELATIONS: dict[tuple[str, str], float] = {
    ("home_win", "over_2_5"): 1.15,
    ("home_win", "btts"): 0.92,
    ("home_win", "ah_home_minus1"): 1.35,
    ("away_win", "over_2_5"): 1.12,
    ("away_win", "btts"): 0.90,
    ("away_win", "ah_home_plus1"): 1.35,
    ("draw", "under_2_5"): 1.18,
    ("draw", "btts"): 0.85,
    ("over_2_5", "btts"): 1.20,
}


def _correlation_factor(m1: str, m2: str) -> float:
    return (
        SGM_CORRELATIONS.get((m1, m2))
        or SGM_CORRELATIONS.get((m2, m1))
        or 1.0
    )


def sgm_probability(legs: list[dict]) -> float:
    if not legs:
        return 0.0
    if len(legs) == 1:
        return legs[0]["probability"]

    base_prob = 1.0
    for leg in legs:
        base_prob *= leg["probability"]

    adjustment = 1.0
    markets = [leg["market"] for leg in legs]
    for i in range(len(markets)):
        for j in range(i + 1, len(markets)):
            adjustment *= _correlation_factor(markets[i], markets[j])

    adjustment = max(0.5, min(2.0, adjustment))
    return min(1.0, base_prob * adjustment)
