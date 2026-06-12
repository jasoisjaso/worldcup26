from backend.betting.kelly import quarter_kelly


def test_no_edge_returns_zero():
    assert quarter_kelly(our_prob=0.50, decimal_odds=2.0) == 0.0


def test_positive_ev_returns_positive_stake():
    stake = quarter_kelly(our_prob=0.60, decimal_odds=2.0)
    assert stake > 0


def test_stake_is_fraction_of_bankroll():
    stake = quarter_kelly(our_prob=0.60, decimal_odds=2.0)
    assert 0 < stake < 1.0


def test_higher_edge_bigger_stake():
    small = quarter_kelly(our_prob=0.55, decimal_odds=2.0)
    large = quarter_kelly(our_prob=0.70, decimal_odds=2.0)
    assert large > small


def test_negative_ev_returns_zero():
    stake = quarter_kelly(our_prob=0.40, decimal_odds=1.80)
    assert stake == 0.0


def test_stake_is_capped():
    # huge nominal edge must still be bounded by the per-bet cap (_MAX_STAKE = 0.05)
    stake = quarter_kelly(our_prob=0.95, decimal_odds=5.0)
    assert stake == 0.05


def test_non_positive_odds_return_zero():
    assert quarter_kelly(our_prob=0.6, decimal_odds=1.0) == 0.0
    assert quarter_kelly(our_prob=0.6, decimal_odds=0.5) == 0.0
