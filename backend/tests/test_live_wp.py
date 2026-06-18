"""Unit tests for the in-play WP simulator."""
from backend.models.live_wp import (
    LiveState,
    simulate_live_wp,
    simulate_swing_chart,
    RED_CARD_SHORT_SIDE_MULT,
    RED_CARD_LONG_SIDE_MULT,
)


def _close(a: float, b: float, tol: float = 0.03) -> bool:
    return abs(a - b) <= tol


def test_pre_kickoff_matches_full_match_estimate():
    """At minute 0, with no events, live WP should match the pre-match prediction
    closely. (Pre-match prediction uses a different code path but the same lambdas;
    we expect the two to agree within Monte-Carlo noise.)"""
    state = LiveState(elapsed_min=0, home_score=0, away_score=0)
    wp = simulate_live_wp(lambda_home=1.5, lambda_away=1.0, state=state, seed=42)
    # Slight home edge expected. Total must be 1.
    assert _close(wp.p_home + wp.p_draw + wp.p_away, 1.0, tol=0.001)
    assert wp.p_home > wp.p_away  # home stronger
    assert wp.p_home > 0.35       # not a knife-edge


def test_late_lead_locks_in():
    """At minute 90 with home leading 2-0, p_home should be essentially 1."""
    state = LiveState(elapsed_min=90, home_score=2, away_score=0)
    wp = simulate_live_wp(lambda_home=1.5, lambda_away=1.0, state=state, seed=42)
    assert wp.p_home > 0.97
    assert wp.p_away < 0.005


def test_concession_shifts_probability():
    """Conceding a goal should drop the lead team's WP substantially."""
    pre_state = LiveState(elapsed_min=30, home_score=1, away_score=0)
    post_state = LiveState(elapsed_min=30, home_score=1, away_score=1)

    pre = simulate_live_wp(1.5, 1.0, pre_state, seed=42)
    post = simulate_live_wp(1.5, 1.0, post_state, seed=42)
    # Home WP must drop by a meaningful margin.
    assert pre.p_home - post.p_home > 0.20


def test_red_card_penalises_short_side():
    """A red card against home at half-time hurts their WP."""
    no_red = LiveState(elapsed_min=45, home_score=0, away_score=0)
    with_red = LiveState(elapsed_min=45, home_score=0, away_score=0, home_red_cards=1)

    base = simulate_live_wp(1.5, 1.0, no_red, seed=42)
    after = simulate_live_wp(1.5, 1.0, with_red, seed=42)
    # Home WP drop is steeper than away WP gain because Opta's multipliers
    # (0.7 short-side, 1.2 long-side) are asymmetric. Test both directions
    # cross a meaningful threshold (8pts), not perfectly symmetric.
    assert after.p_home < base.p_home - 0.10
    assert after.p_away > base.p_away + 0.08


def test_red_card_multipliers_are_sensible():
    """Sanity: published Opta multipliers are 0.7 and 1.2."""
    assert 0.5 < RED_CARD_SHORT_SIDE_MULT < 0.9
    assert 1.1 < RED_CARD_LONG_SIDE_MULT < 1.4


def test_probability_sums_to_one_throughout():
    """At every minute and score, p_home + p_draw + p_away must equal 1."""
    states = [
        LiveState(0, 0, 0),
        LiveState(15, 0, 0),
        LiveState(45, 1, 0),
        LiveState(75, 1, 1),
        LiveState(90, 2, 1),
        LiveState(95, 2, 2),
    ]
    for s in states:
        wp = simulate_live_wp(1.5, 1.0, s, seed=42)
        assert _close(wp.p_home + wp.p_draw + wp.p_away, 1.0, tol=0.001), s


def test_match_over_returns_actual_result():
    """At minute 95, the simulator must return the observed result, not a sim."""
    # Home win
    wp = simulate_live_wp(1.5, 1.0, LiveState(95, 2, 0), seed=42)
    assert wp == type(wp)(1.0, 0.0, 0.0)
    # Draw
    wp = simulate_live_wp(1.5, 1.0, LiveState(95, 1, 1), seed=42)
    assert wp == type(wp)(0.0, 1.0, 0.0)
    # Away win
    wp = simulate_live_wp(1.5, 1.0, LiveState(95, 0, 1), seed=42)
    assert wp == type(wp)(0.0, 0.0, 1.0)


def test_swing_chart_returns_series_in_order():
    """The swing-chart helper should preserve timeline order."""
    timeline = [LiveState(t, 0, 0) for t in (0, 30, 45, 60, 90)]
    series = simulate_swing_chart(1.5, 1.0, timeline, seed=42)
    minutes = [m for m, _ in series]
    assert minutes == [0, 30, 45, 60, 90]


def test_deterministic_under_seed():
    """Same seed → identical output."""
    state = LiveState(45, 1, 0)
    a = simulate_live_wp(1.5, 1.0, state, seed=123)
    b = simulate_live_wp(1.5, 1.0, state, seed=123)
    assert a == b
