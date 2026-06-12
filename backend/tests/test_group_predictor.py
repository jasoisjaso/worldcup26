import math

from backend.models.group_predictor import (
    predict_group_match, TeamInput, _capped_multiplier, _MOD_LOG_CAP,
)
from backend.models.match_context import md1_rho, DEFAULT_RHO


def _team(elo, code):
    return TeamInput(elo=elo, form=[], chance_quality=1.3, code=code)


def test_capped_multiplier_equals_product_within_cap():
    mults = (0.98, 1.02, 0.99, 1.01)
    assert math.isclose(_capped_multiplier(mults), math.prod(mults), rel_tol=1e-9)


def test_capped_multiplier_clamps_extreme_stack():
    # nine 0.5 factors would be 0.5**9 ≈ 0.00195 uncapped
    capped = _capped_multiplier((0.5,) * 9)
    assert math.isclose(capped, math.exp(-_MOD_LOG_CAP), rel_tol=1e-9)
    assert 0.77 < capped < 0.79
    capped_up = _capped_multiplier((1.5,) * 9)
    assert math.isclose(capped_up, math.exp(_MOD_LOG_CAP), rel_tol=1e-9)


def test_capped_multiplier_neutral():
    assert _capped_multiplier((1.0,) * 9) == 1.0


def test_predict_probabilities_valid_and_ordered():
    p = predict_group_match(_team(2000, "fr"), _team(1400, "ht"))
    total = p.home_win + p.draw + p.away_win
    assert math.isclose(total, 1.0, abs_tol=1e-6)
    assert p.home_win > p.away_win  # much stronger home is favoured
    assert 0.0 <= p.over_2_5 <= 1.0


def test_extreme_modifiers_cannot_blow_up_lambda():
    # even with every multiplicative modifier at 0.5, the combined effect is bounded,
    # so lambdas stay in a range the score matrix was calibrated for
    p = predict_group_match(
        _team(1600, "fr"), _team(1600, "de"),
        rest_multipliers=(0.5, 0.5), dead_rubber_multipliers=(0.5, 0.5),
        squad_quality_multipliers=(0.5, 0.5), injury_multipliers=(0.5, 0.5),
        h2h_multipliers=(0.5, 0.5), weather_multipliers=(0.5, 0.5),
        travel_multipliers=(0.5, 0.5), lineup_multipliers=(0.5, 0.5),
        xg_multipliers=(0.5, 0.5),
    )
    # base ~1.3 each; capped multiplier floor ~0.78 => lambda no lower than ~1.0
    assert p.lambda_home > 0.9
    assert math.isclose(p.home_win + p.draw + p.away_win, 1.0, abs_tol=1e-3)


def test_md1_rho_no_longer_special_cased():
    assert md1_rho(1) == DEFAULT_RHO
    assert md1_rho(2) == DEFAULT_RHO
    assert md1_rho(None) == DEFAULT_RHO
