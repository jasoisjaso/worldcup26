from dataclasses import dataclass
from backend.models.elo_model import elo_to_lambdas
from backend.models.form import form_modifier
from backend.models.poisson import (
    build_score_matrix,
    match_probabilities,
    over_under_probability,
    btts_probability,
    top_scores,
    asian_handicap_probability,
)


@dataclass
class TeamInput:
    elo: float
    form: list[tuple[str, str]]
    chance_quality: float
    code: str = ""


@dataclass
class MatchPrediction:
    home_win: float
    draw: float
    away_win: float
    over_2_5: float
    under_2_5: float
    btts: float
    ah_home_minus1: float
    ah_home_plus1: float
    top_scores: list[dict]
    lambda_home: float
    lambda_away: float
    why_factors: list[dict]
    expected_corners: float
    expected_cards: float


def predict_group_match(
    home: TeamInput,
    away: TeamInput,
    venue_context: dict | None = None,
    matchday: int | None = None,
    altitude_bonus: float = 0.0,
    rest_multipliers: tuple[float, float] = (1.0, 1.0),
    dead_rubber_multipliers: tuple[float, float] = (1.0, 1.0),
    squad_quality_multipliers: tuple[float, float] = (1.0, 1.0),
    injury_multipliers: tuple[float, float] = (1.0, 1.0),
    h2h_multipliers: tuple[float, float] = (1.0, 1.0),
    weather_multipliers: tuple[float, float] = (1.0, 1.0),
    travel_multipliers: tuple[float, float] = (1.0, 1.0),
    lineup_multipliers: tuple[float, float] = (1.0, 1.0),
    xg_multipliers: tuple[float, float] = (1.0, 1.0),
) -> MatchPrediction:
    from backend.models.match_context import md1_rho as _md1_rho

    lh, la = elo_to_lambdas(home.elo, away.elo, home.code, away.code)

    # Altitude: additive to both (both teams score more at high altitude)
    lh += altitude_bonus
    la += altitude_bonus

    # Form: additive
    lh = max(0.1, lh + form_modifier(home.form))
    la = max(0.1, la + form_modifier(away.form))

    # Multiplicative context modifiers — applied in order of volatility
    lh = max(0.1, lh * rest_multipliers[0] * dead_rubber_multipliers[0]
             * squad_quality_multipliers[0] * injury_multipliers[0]
             * h2h_multipliers[0] * weather_multipliers[0] * travel_multipliers[0]
             * lineup_multipliers[0] * xg_multipliers[0])
    la = max(0.1, la * rest_multipliers[1] * dead_rubber_multipliers[1]
             * squad_quality_multipliers[1] * injury_multipliers[1]
             * h2h_multipliers[1] * weather_multipliers[1] * travel_multipliers[1]
             * lineup_multipliers[1] * xg_multipliers[1])

    rho = _md1_rho(matchday)
    matrix = build_score_matrix(lh, la, rho=rho)
    probs = match_probabilities(matrix)
    ou = over_under_probability(matrix, line=2.5)
    ah_m1 = asian_handicap_probability(matrix, line=-1.0)
    ah_p1 = asian_handicap_probability(matrix, line=1.0)

    # Corner model (arxiv:2112.13001): WC average ~9.5, scales with goal expectation
    TG = lh + la
    SUP = abs(lh - la)
    expected_corners = round(6.5 + TG + 1.2 * SUP, 1)

    # Card model: tension peaks when teams are evenly matched
    tension = 1.0 - abs(probs["home_win"] - probs["away_win"])
    expected_cards = round(2.8 + 2.0 * tension, 1)

    why = _build_why_factors(home, away, lh, la, venue_context=venue_context, matchday=matchday)

    return MatchPrediction(
        home_win=round(probs["home_win"], 4),
        draw=round(probs["draw"], 4),
        away_win=round(probs["away_win"], 4),
        over_2_5=round(ou["over"], 4),
        under_2_5=round(ou["under"], 4),
        btts=round(btts_probability(matrix), 4),
        ah_home_minus1=round(ah_m1["home_covers"], 4),
        ah_home_plus1=round(ah_p1["home_covers"], 4),
        top_scores=top_scores(matrix, n=6),
        lambda_home=round(lh, 3),
        lambda_away=round(la, 3),
        why_factors=why,
        expected_corners=expected_corners,
        expected_cards=expected_cards,
    )


def _build_why_factors(
    home: TeamInput,
    away: TeamInput,
    lh: float,
    la: float,
    venue_context: dict | None = None,
    matchday: int | None = None,
) -> list[dict]:
    factors = []
    elo_diff = home.elo - away.elo
    if abs(elo_diff) > 50:
        direction = "positive" if elo_diff > 0 else "negative"
        label = f"Strength rating edge: {abs(int(elo_diff))} points {'in favour' if elo_diff > 0 else 'against'}"
        factors.append({"label": label, "direction": direction})

    home_form = form_modifier(home.form)
    away_form = form_modifier(away.form)
    if home_form >= 0.10:
        factors.append({"label": "Strong recent form", "direction": "positive"})
    elif home_form <= -0.10:
        factors.append({"label": "Poor recent form", "direction": "negative"})

    if away_form >= 0.10:
        factors.append({"label": "Opposition in good form", "direction": "negative"})

    if abs(home.chance_quality - away.chance_quality) > 0.2:
        better = "home" if home.chance_quality > away.chance_quality else "away"
        factors.append({
            "label": f"Chance quality advantage to {'this team' if better == 'home' else 'opposition'}",
            "direction": "positive" if better == "home" else "negative",
        })

    if venue_context:
        hb = venue_context.get("home_bonus", 0)
        ab = venue_context.get("away_bonus", 0)
        if hb >= 50:
            factors.append({"label": f"Host nation home crowd advantage (+{int(hb)} pts)", "direction": "positive"})
        elif hb > 0:
            factors.append({"label": f"Diaspora crowd support (+{int(hb)} pts)", "direction": "positive"})
        elif hb < 0:
            factors.append({"label": f"High altitude / travel fatigue penalty ({int(hb)} pts)", "direction": "negative"})
        if ab >= 50:
            factors.append({"label": f"Opposition playing on home soil (+{int(ab)} pts)", "direction": "negative"})
        elif ab > 0:
            factors.append({"label": f"Strong diaspora following for opposition (+{int(ab)} pts)", "direction": "negative"})
        elif ab < 0:
            factors.append({"label": f"Opposition altitude / travel penalty ({int(ab)} pts)", "direction": "positive"})
        if hb == 0 and ab == 0:
            factors.append({"label": "Neutral ground, no significant crowd advantage", "direction": "neutral"})
    else:
        factors.append({"label": "Neutral ground, no significant crowd advantage", "direction": "neutral"})

    if matchday == 3:
        factors.append({
            "label": "MD3 rotation risk: squads may rest starters if qualification already settled",
            "direction": "neutral",
        })

    return factors
