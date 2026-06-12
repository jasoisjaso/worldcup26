# Hard cap on any single stake as a fraction of bankroll. The model probability is only
# approximately calibrated, and Kelly is acutely sensitive to over-estimated edge, so we
# bound the downside of one bad input regardless of how large the nominal edge looks.
_MAX_STAKE = 0.05


def quarter_kelly(our_prob: float, decimal_odds: float) -> float:
    b = decimal_odds - 1.0
    if b <= 0:
        return 0.0
    p = max(0.0, min(1.0, our_prob))
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    full_kelly = min(full_kelly, 1.0)
    return round(min(full_kelly * 0.25, _MAX_STAKE), 4)
