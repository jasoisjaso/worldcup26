"""Sanity tests for the anytime-goalscorer market math.

Pure math only — the DB-bound `_team_anytime_goalscorers` is exercised
end-to-end against the live database in production, but the per-player
Poisson + position-share + recency-boost logic must hold in isolation.
"""
from __future__ import annotations

import pytest

from backend.betting import goalscorer_markets as gm


def test_position_share_known_keys():
    """Each position has a documented prior — verify the strikers > mids > defs ordering."""
    assert gm._position_share("Attacker") > gm._position_share("Midfielder")
    assert gm._position_share("Midfielder") > gm._position_share("Defender")
    assert gm._position_share("Defender") > gm._position_share("Goalkeeper")


def test_position_share_unknown_falls_back():
    """Unknown / null positions get the midfielder middle prior so they're
    never accidentally weighted as strikers (would create false positives)."""
    assert gm._position_share(None) == gm._POSITION_SHARE["midfielder"]
    assert gm._position_share("") == gm._POSITION_SHARE["midfielder"]
    assert gm._position_share("Coach") == gm._POSITION_SHARE["midfielder"]


def test_p_score_monotonic_in_expected_goals():
    """More expected goals → higher P(scores ≥ 1). Sanity."""
    assert gm._p_score(0.0) == 0.0
    assert gm._p_score(0.1) < gm._p_score(0.3) < gm._p_score(1.0)
    # P(score ≥ 1) for λ=1 ≈ 0.632
    assert abs(gm._p_score(1.0) - 0.632) < 0.01


def test_recency_boost_caps():
    """Past _RECENCY_CAP a hot streak shouldn't push the player into
    nonsensical territory — boost stays bounded."""
    # 10 goals + 1.0 base + 0.15 per goal = 2.5, but capped at 1.8
    eg = gm._expected_player_goals(team_lambda=1.3, position="Attacker", recent_goals=10)
    eg_5 = gm._expected_player_goals(team_lambda=1.3, position="Attacker", recent_goals=5)
    # 5 goals: 1.0 + 0.75 = 1.75 (just under cap)
    # 10 goals: capped at 1.8 → only marginally higher
    assert eg / eg_5 < 1.1  # not absurdly different


def test_striker_outscores_defender_at_same_team_lambda():
    """A striker on a 2.0-λ team must outscore a defender on the same team."""
    striker = gm._expected_player_goals(team_lambda=2.0, position="Attacker", recent_goals=0)
    defender = gm._expected_player_goals(team_lambda=2.0, position="Defender", recent_goals=0)
    assert striker > 5 * defender  # at least 5× higher (0.30 vs 0.03 share)


def test_p_score_zero_for_gk_with_no_goals():
    """GK with no goals: expected_goals ≈ team_lambda × 0.001 → tiny p."""
    eg = gm._expected_player_goals(team_lambda=2.0, position="Goalkeeper", recent_goals=0)
    p = gm._p_score(eg)
    assert p < 0.005  # below display threshold


@pytest.mark.parametrize("lam", [0.5, 1.0, 1.5, 2.5, 3.5])
def test_team_lambda_scales_expected_goals_linearly(lam):
    """Doubling team_lambda should ~double per-player expected goals
    (linear scaling via the normalisation factor)."""
    base = gm._expected_player_goals(team_lambda=lam, position="Attacker", recent_goals=0)
    doubled = gm._expected_player_goals(team_lambda=lam * 2, position="Attacker", recent_goals=0)
    assert abs(doubled / base - 2.0) < 0.01


def test_fair_odds_format():
    """Fair odds: 1/p, rounded, capped at 1000."""
    assert gm._fair(0.5) == 2.0
    assert gm._fair(0.10) == 10.0
    assert gm._fair(0.001) == 1000
    assert gm._fair(0.0001) is None  # past cap
    assert gm._fair(0.0) is None


def test_recent_goals_boost_within_cap():
    """Each recent goal nudges the estimate up — but only up to the cap."""
    no_goals = gm._expected_player_goals(team_lambda=1.3, position="Attacker", recent_goals=0)
    one_goal = gm._expected_player_goals(team_lambda=1.3, position="Attacker", recent_goals=1)
    three_goals = gm._expected_player_goals(team_lambda=1.3, position="Attacker", recent_goals=3)
    assert no_goals < one_goal < three_goals
    # 1 goal → 1.15× boost over no goals
    assert abs(one_goal / no_goals - 1.15) < 0.01
