from backend.models.dc_ratings import get_lambdas as _dc_get_lambdas

# Confederation strength offsets applied before cross-confederation ELO comparison.
# Tapered by within-WC ELO rank percentile × 0.60 scalar — weaker qualifiers within
# a strong confederation get a reduced boost; formula: base × (1 - pct × 0.60).
# When teams share a confederation the offsets cancel — adjustment only shifts cross-conf diff.
CONFED_OFFSETS: dict[str, int] = {
    # UEFA (base +117, tapered by within-WC ELO rank)
    "fr": 117, "es": 112, "pt": 108, "de": 103, "nl": 98,
    "be": 94, "gb-eng": 89, "hr": 84, "ch": 80, "tr": 75,
    "at": 70, "no": 66, "cz": 61, "gb-sct": 56, "ba": 51, "se": 47,
    # CONMEBOL (base +104, tapered)
    "ar": 104, "br": 92, "co": 79, "uy": 67, "ec": 54, "py": 42,
    # AFC (base +18, tapered — small range so minimal practical difference)
    "jp": 18, "ir": 17, "kr": 15, "au": 14,
    "sa": 13, "uz": 11, "qa": 10, "jo": 9, "iq": 7,
    # CONCACAF (base -27, tapered — penalty shrinks for better qualifiers)
    "mx": -27, "us": -24, "ca": -21, "pa": -17, "cw": -14, "ht": -11,
    # CAF (base -40, tapered)
    "ma": -40, "sn": -37, "eg": -35, "ci": -32, "dz": -29,
    "tn": -27, "cd": -24, "za": -21, "gh": -19, "cv": -16,
    # OFC
    "nz": -171,
}


def elo_to_lambdas(
    home_elo: float,
    away_elo: float,
    home_code: str = "",
    away_code: str = "",
) -> tuple[float, float]:
    # Use fitted Dixon-Coles attack/defense params when available (both teams must be in the dataset).
    dc = _dc_get_lambdas(home_code, away_code)
    if dc is not None:
        return dc

    # ELO fallback: used only when one or both teams lack DC history.
    home_adj = home_elo + CONFED_OFFSETS.get(home_code, 0)
    away_adj = away_elo + CONFED_OFFSETS.get(away_code, 0)
    diff = home_adj - away_adj
    home_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    BASE_GOALS = 1.3
    SCALE = 2.0
    lambda_home = max(0.1, BASE_GOALS + SCALE * (home_win_prob - 0.5))
    lambda_away = max(0.1, BASE_GOALS - SCALE * (home_win_prob - 0.5))
    return lambda_home, lambda_away
