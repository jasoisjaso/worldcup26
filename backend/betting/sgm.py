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
    markets = [l["market"] for l in legs]
    for i in range(len(markets)):
        for j in range(i + 1, len(markets)):
            adjustment *= _correlation_factor(markets[i], markets[j])

    adjustment = max(0.5, min(2.0, adjustment))
    return min(1.0, base_prob * adjustment)
