import math

from backend.betting.market import (
    devig_shin, blend_three_way, blend_two_way, closing_line_value,
)


def test_shin_sums_to_one():
    p = devig_shin([1.5, 4.0, 7.0])
    assert p is not None
    assert math.isclose(sum(p), 1.0, abs_tol=1e-9)


def test_shin_corrects_favourite_longshot_bias():
    odds = [1.5, 4.0, 7.0]
    imp = [1 / o for o in odds]
    B = sum(imp)
    prop = [i / B for i in imp]
    shin = devig_shin(odds)
    # Shin lifts the favourite and trims the longshot vs proportional de-vig.
    assert shin[0] > prop[0]
    assert shin[2] < prop[2]


def test_shin_no_vig_passthrough():
    p = devig_shin([2.0, 2.0])
    assert p == [0.5, 0.5]


def test_shin_rejects_bad_odds():
    assert devig_shin([1.0, 2.0]) is None
    assert devig_shin([]) is None
    assert devig_shin([None, 2.0]) is None


def test_blend_returns_model_without_odds():
    assert blend_three_way(0.5, 0.3, 0.2, None) == (0.5, 0.3, 0.2)
    assert blend_three_way(0.5, 0.3, 0.2, {"home_win": 2.0}) == (0.5, 0.3, 0.2)


def test_blend_three_way_pulls_toward_market_and_normalizes():
    odds = {"home_win": 1.5, "draw": 4.0, "away_win": 7.0}
    h, d, a = blend_three_way(0.40, 0.30, 0.30, odds)
    assert math.isclose(h + d + a, 1.0, abs_tol=1e-3)
    # market favours home strongly, so blended home prob exceeds the 0.40 model prob
    assert h > 0.40


def test_blend_two_way_passthrough_and_blend():
    assert blend_two_way(0.55, 0.45, None, None) == (0.55, 0.45)
    o, u = blend_two_way(0.55, 0.45, 1.9, 1.9)
    assert math.isclose(o + u, 1.0, abs_tol=1e-3)


def test_clv_positive_when_bet_beats_close():
    # Closing fair line ~ even (50/50 after de-vig); we bet home at 2.40 -> beat the close.
    close = {"home_win": 1.95, "draw": 3.6, "away_win": 4.2}
    close_dec, clv = closing_line_value("home_win", 2.40, close)
    assert close_dec == 1.95
    assert clv is not None and clv > 0


def test_clv_negative_when_bet_worse_than_close():
    # We bet home at only 1.50 but the close implies home is far from a 1/1.5 = 66% shot.
    close = {"home_win": 2.10, "draw": 3.3, "away_win": 3.5}
    _close_dec, clv = closing_line_value("home_win", 1.50, close)
    assert clv is not None and clv < 0


def test_clv_none_without_market_line():
    assert closing_line_value("home_win", 2.0, None) == (None, None)
    assert closing_line_value("home_win", 2.0, {"draw": 3.0}) == (None, None)
    # BTTS has no complementary price in the book -> closing odds captured, CLV not scorable
    close_dec, clv = closing_line_value("btts", 1.8, {"btts": 1.8})
    assert close_dec == 1.8 and clv is None
