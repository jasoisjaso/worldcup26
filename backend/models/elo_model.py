# Confederation strength offsets applied before cross-confederation ELO comparison.
# Source: backtested on 8,021 international matches (2018-2026), worldcup-predictor methodology.
# When teams share a confederation the offsets cancel — adjustment only shifts cross-conf diff.
CONFED_OFFSETS: dict[str, int] = {
    # UEFA +117
    "at": 117, "ba": 117, "be": 117, "hr": 117, "cz": 117,
    "gb-eng": 117, "fr": 117, "de": 117, "nl": 117, "no": 117,
    "pt": 117, "gb-sct": 117, "es": 117, "se": 117, "ch": 117, "tr": 117,
    # CONMEBOL +104
    "ar": 104, "br": 104, "co": 104, "ec": 104, "py": 104, "uy": 104,
    # AFC +18
    "au": 18, "ir": 18, "iq": 18, "jp": 18, "jo": 18,
    "qa": 18, "sa": 18, "kr": 18, "uz": 18,
    # CONCACAF -27
    "ca": -27, "cw": -27, "ht": -27, "mx": -27, "pa": -27, "us": -27,
    # CAF -40
    "dz": -40, "cv": -40, "cd": -40, "eg": -40, "gh": -40,
    "ci": -40, "ma": -40, "sn": -40, "za": -40, "tn": -40,
    # OFC -171
    "nz": -171,
}


def elo_to_lambdas(
    home_elo: float,
    away_elo: float,
    home_code: str = "",
    away_code: str = "",
) -> tuple[float, float]:
    home_adj = home_elo + CONFED_OFFSETS.get(home_code, 0)
    away_adj = away_elo + CONFED_OFFSETS.get(away_code, 0)
    diff = home_adj - away_adj
    home_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    BASE_GOALS = 1.3
    SCALE = 2.0
    lambda_home = max(0.1, BASE_GOALS + SCALE * (home_win_prob - 0.5))
    lambda_away = max(0.1, BASE_GOALS - SCALE * (home_win_prob - 0.5))
    return lambda_home, lambda_away
