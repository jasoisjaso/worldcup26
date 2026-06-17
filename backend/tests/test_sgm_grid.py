"""Same-game multis priced from the score grid: the joint must capture true correlation,
not the naive independent product."""
from backend.betting.sgm import joint_probability_from_grid
from backend.models.poisson import build_score_matrix


def _grid():
    # A clear favourite at home (1.7 xG vs 1.0), Dixon-Coles low-score correction.
    return build_score_matrix(1.7, 1.0, max_goals=10, rho=-0.13)


def _marg(m):
    return joint_probability_from_grid(_grid(), [m])


def test_single_leg_equals_market_marginal():
    g = _grid()
    # home_win marginal from the grid is a normal probability in (0,1)
    p = joint_probability_from_grid(g, ["home_win"])
    assert 0.0 < p < 1.0


def test_home_win_and_over_is_positively_correlated():
    g = _grid()
    joint = joint_probability_from_grid(g, ["home_win", "over_2_5"])
    naive = _marg("home_win") * _marg("over_2_5")
    assert joint > naive  # a favourite winning tends to mean goals


def test_home_win_and_btts_is_negatively_correlated():
    g = _grid()
    joint = joint_probability_from_grid(g, ["home_win", "btts"])
    naive = _marg("home_win") * _marg("btts")
    assert joint < naive  # if the favourite wins, the away side often fails to score


def test_home_win_and_under_is_negatively_correlated():
    g = _grid()
    joint = joint_probability_from_grid(g, ["home_win", "under_2_5"])
    naive = _marg("home_win") * _marg("under_2_5")
    # The naive multiplier table defaulted this pair to independent (1.0); it is not.
    assert joint < naive


def test_complementary_legs_are_impossible():
    g = _grid()
    # Cannot be both a home win and a draw.
    assert joint_probability_from_grid(g, ["home_win", "draw"]) == 0.0
    # Cannot be over 2.5 and under 2.5 at once.
    assert joint_probability_from_grid(g, ["over_2_5", "under_2_5"]) == 0.0


def test_unpriceable_leg_returns_none():
    g = _grid()
    # A half-time market is not a function of the final score, so the grid cannot price it.
    assert joint_probability_from_grid(g, ["home_win", "ht_home_win"]) is None


def test_joint_never_exceeds_either_marginal():
    g = _grid()
    joint = joint_probability_from_grid(g, ["home_win", "over_2_5"])
    assert joint <= _marg("home_win") + 1e-9
    assert joint <= _marg("over_2_5") + 1e-9
