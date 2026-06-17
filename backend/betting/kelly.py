# Hard cap on any single stake as a fraction of bankroll. The model probability is only
# approximately calibrated, and Kelly is acutely sensitive to over-estimated edge, so we
# bound the downside of one bad input regardless of how large the nominal edge looks.
_MAX_STAKE = 0.05


def _fractional_kelly(our_prob: float, decimal_odds: float, fraction: float) -> float:
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    p = max(0.0, min(1.0, our_prob))
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    full_kelly = min(full_kelly, 1.0)
    return round(min(full_kelly * fraction, _MAX_STAKE), 4)


def quarter_kelly(our_prob: float, decimal_odds: float) -> float:
    return _fractional_kelly(our_prob, decimal_odds, 0.25)


def multi_kelly(combined_prob: float, combined_odds: float, n_legs: int) -> float:
    """Kelly for a multi, treated as the single binary bet it is (combined prob and odds).

    A multi compounds the model's own bias to the n-th power: if the goal model is even
    slightly off on each leg, the error multiplies, so the true edge is more uncertain than
    the headline number. We therefore stake multis on a heavier fractional Kelly than
    singles, shrinking further with each extra leg, and keep the same hard 5% cap.
    """
    fraction = 0.25 if n_legs <= 2 else (0.15 if n_legs == 3 else 0.10)
    return _fractional_kelly(combined_prob, combined_odds, fraction)
