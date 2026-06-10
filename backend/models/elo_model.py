def elo_to_lambdas(home_elo: float, away_elo: float) -> tuple[float, float]:
    """Convert ELO ratings to Poisson lambda values. Neutral ground assumed."""
    diff = home_elo - away_elo
    home_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    BASE_GOALS = 1.3
    SCALE = 2.0
    lambda_home = max(0.1, BASE_GOALS + SCALE * (home_win_prob - 0.5))
    lambda_away = max(0.1, BASE_GOALS - SCALE * (home_win_prob - 0.5))
    return lambda_home, lambda_away
