from backend.models.dc_ratings import get_lambdas as _dc_get_lambdas

# DC<->ELO blend weights (fraction given to DC). Walk-forward backtest
# (backend/eval/backtest.py, ~1500 OOS internationals) shows the blend RPS optimum
# is a flat 0.4-0.6 DC, and pure ELO already edges pure DC — the previous 0.75/0.50
# over-weighted DC, exactly the component that is unreliable cross-confederation.
# Shifted toward ELO; cross-conf kept lower since that is DC's documented weak spot.
# See memory: wc2026-model-findings.
DC_WEIGHT_SAME_CONF = 0.55
DC_WEIGHT_CROSS_CONF = 0.45

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
    # ELO-based lambdas with confederation quality correction.
    home_adj = home_elo + CONFED_OFFSETS.get(home_code, 0)
    away_adj = away_elo + CONFED_OFFSETS.get(away_code, 0)
    diff = home_adj - away_adj
    home_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    BASE_GOALS = 1.3
    SCALE = 2.0
    lambda_home_elo = max(0.1, BASE_GOALS + SCALE * (home_win_prob - 0.5))
    lambda_away_elo = max(0.1, BASE_GOALS - SCALE * (home_win_prob - 0.5))

    dc = _dc_get_lambdas(home_code, away_code)
    if dc is None:
        return lambda_home_elo, lambda_away_elo

    # DC params are calibrated within-confederation but overrate/underrate teams in
    # cross-confederation matchups (e.g. Algeria beta=-0.996 from beating weak CAF
    # sides looks equal to France's defensive record against UEFA teams).
    # Blend DC with ELO; cross-confederation leans harder on ELO (see weights above).
    home_offset = CONFED_OFFSETS.get(home_code, 0)
    away_offset = CONFED_OFFSETS.get(away_code, 0)
    cross_conf = abs(home_offset - away_offset) > 50
    dc_weight = DC_WEIGHT_CROSS_CONF if cross_conf else DC_WEIGHT_SAME_CONF
    lh = dc_weight * dc[0] + (1.0 - dc_weight) * lambda_home_elo
    la = dc_weight * dc[1] + (1.0 - dc_weight) * lambda_away_elo
    return lh, la


# --- model-uncertainty signal ----------------------------------------------
# The engine has two independent views of a match: ELO-derived lambdas and the
# DC fitted lambdas. Where they disagree strongly we are genuinely less sure —
# a free, no-dependency "trust this less" flag. (ClubElo, the obvious external
# second-opinion, is CLUB-only and useless for a World Cup, so we derive the
# uncertainty internally from the two views the model already computes.)

# Divergence thresholds on the summed-goal disagreement between the two views.
_UNCERTAINTY_MODERATE = 0.45
_UNCERTAINTY_HIGH = 0.90


def elo_only_lambdas(home_elo: float, away_elo: float, home_code: str = "", away_code: str = "") -> tuple[float, float]:
    """The pure ELO view (no DC blend) — one of the two opinions we compare."""
    home_adj = home_elo + CONFED_OFFSETS.get(home_code, 0)
    away_adj = away_elo + CONFED_OFFSETS.get(away_code, 0)
    diff = home_adj - away_adj
    home_win_prob = 1.0 / (1.0 + 10.0 ** (-diff / 400.0))
    BASE_GOALS = 1.3
    SCALE = 2.0
    return (
        max(0.1, BASE_GOALS + SCALE * (home_win_prob - 0.5)),
        max(0.1, BASE_GOALS - SCALE * (home_win_prob - 0.5)),
    )


def dc_only_lambdas(home_code: str, away_code: str) -> tuple[float, float] | None:
    """The pure DC fitted view, or None if either team has no fitted params."""
    return _dc_get_lambdas(home_code, away_code)


def lambda_divergence(elo: tuple[float, float], dc: tuple[float, float]) -> float:
    """How far the two views disagree, in goals. We compare the goal SUPREMACY
    (home minus away) of each view — that's what actually moves the 1X2 — plus a
    smaller term for total-goals disagreement. Symmetric, >= 0."""
    elo_sup = elo[0] - elo[1]
    dc_sup = dc[0] - dc[1]
    sup_gap = abs(elo_sup - dc_sup)
    total_gap = abs((elo[0] + elo[1]) - (dc[0] + dc[1]))
    return round(sup_gap + 0.5 * total_gap, 4)


def uncertainty_flag(elo: tuple[float, float], dc: tuple[float, float] | None) -> str | None:
    """Tier the divergence into confident / moderate / uncertain. None when we
    have no DC view to compare against (so we never fake confidence)."""
    if dc is None:
        return None
    d = lambda_divergence(elo, dc)
    if d >= _UNCERTAINTY_HIGH:
        return "uncertain"
    if d >= _UNCERTAINTY_MODERATE:
        return "moderate"
    return "confident"
