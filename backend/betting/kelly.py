def quarter_kelly(our_prob: float, decimal_odds: float) -> float:
    b = decimal_odds - 1.0
    p = our_prob
    q = 1.0 - p
    full_kelly = (b * p - q) / b
    if full_kelly <= 0:
        return 0.0
    return round(full_kelly * 0.25, 4)
