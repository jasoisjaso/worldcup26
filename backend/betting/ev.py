def calculate_ev(our_probability: float, decimal_odds: float) -> float:
    return round((our_probability * decimal_odds) - 1.0, 4)


def strip_margin(odds_list: list[float]) -> list[float]:
    implied = [1.0 / o for o in odds_list]
    total = sum(implied)
    return [i / total for i in implied]


def true_probability(decimal_odds: float, market_odds: list[float]) -> float:
    implied = [1.0 / o for o in market_odds]
    total = sum(implied)
    return (1.0 / decimal_odds) / total
