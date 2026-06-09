from backend.betting.ev import calculate_ev, strip_margin, true_probability


def test_zero_ev_at_exact_odds():
    assert abs(calculate_ev(0.5, 2.0)) < 0.001


def test_positive_ev_when_underpriced():
    ev = calculate_ev(0.60, 2.0)
    assert ev > 0


def test_negative_ev_when_overpriced():
    ev = calculate_ev(0.40, 1.80)
    assert ev < 0


def test_strip_margin_sums_to_one():
    fair = strip_margin([2.20, 3.40, 3.00])
    assert abs(sum(fair) - 1.0) < 0.001


def test_strip_margin_preserves_order():
    odds = [1.80, 3.40, 4.50]
    fair = strip_margin(odds)
    assert fair[0] > fair[1] > fair[2]


def test_true_probability_single_outcome():
    p = true_probability(1.80, [1.80, 3.40, 4.50])
    assert 0.50 < p < 0.55
