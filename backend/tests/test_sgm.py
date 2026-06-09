from backend.betting.sgm import sgm_probability, SGM_CORRELATIONS


def test_single_leg_unchanged():
    legs = [{"market": "home_win", "probability": 0.65}]
    assert abs(sgm_probability(legs) - 0.65) < 0.001


def test_independent_legs_multiply():
    legs = [
        {"market": "home_win", "probability": 0.60},
        {"market": "draw", "probability": 0.25},
    ]
    result = sgm_probability(legs)
    assert 0.0 <= result <= 1.0


def test_positive_correlation_increases_probability():
    base = 0.60 * 0.55
    legs = [
        {"market": "home_win", "probability": 0.60},
        {"market": "over_2_5", "probability": 0.55},
    ]
    result = sgm_probability(legs)
    assert result > base


def test_result_bounded_zero_to_one():
    legs = [
        {"market": "home_win", "probability": 0.90},
        {"market": "over_2_5", "probability": 0.85},
        {"market": "btts", "probability": 0.70},
    ]
    result = sgm_probability(legs)
    assert 0.0 <= result <= 1.0


def test_correlation_table_has_expected_entries():
    assert ("home_win", "over_2_5") in SGM_CORRELATIONS
    assert ("home_win", "btts") in SGM_CORRELATIONS
    assert ("draw", "under_2_5") in SGM_CORRELATIONS
