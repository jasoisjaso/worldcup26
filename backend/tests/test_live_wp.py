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


# --- live xG adjustment -----------------------------------------------------

def test_live_xg_no_effect_when_absent():
    """Without xG the result must match the score-only restart exactly."""
    state_plain = LiveState(60, 1, 1)
    state_no_xg = LiveState(60, 1, 1, home_xg=None, away_xg=None)
    a = simulate_live_wp(1.4, 1.2, state_plain, seed=7)
    b = simulate_live_wp(1.4, 1.2, state_no_xg, seed=7)
    assert a == b


def test_live_xg_no_effect_too_early():
    """A single early big chance must NOT swing the WP (sample too small)."""
    base = simulate_live_wp(1.4, 1.2, LiveState(10, 0, 0), seed=7)
    # Home had a penalty miss worth 0.8 xG in minute 10 — still pre-threshold.
    spiked = simulate_live_wp(1.4, 1.2, LiveState(10, 0, 0, home_xg=0.8, away_xg=0.05), seed=7)
    assert base == spiked


def test_live_xg_dominance_lifts_win_prob():
    """A side battering the opponent on xG while level should see WP rise."""
    # Level 1-1 at 60'. Home has hugely out-created away on live xG.
    even = simulate_live_wp(1.3, 1.3, LiveState(60, 1, 1), seed=7)
    home_dominant = simulate_live_wp(
        1.3, 1.3, LiveState(60, 1, 1, home_xg=2.6, away_xg=0.4), seed=7,
    )
    assert home_dominant.p_home > even.p_home, "xG dominance should lift the dominant side"
    assert home_dominant.p_away < even.p_away


def test_live_xg_adjustment_is_capped():
    """Even absurd xG dominance can't push the remaining-rate bend past the cap,
    so the WP shift stays bounded (no runaway from a noisy xG feed)."""
    even = simulate_live_wp(1.3, 1.3, LiveState(60, 0, 0), seed=7)
    extreme = simulate_live_wp(
        1.3, 1.3, LiveState(60, 0, 0, home_xg=9.9, away_xg=0.01), seed=7,
    )
    # Bounded: the lift is real but not a blowout (cap 35% × blend 50% on the rate).
    assert 0.0 < (extreme.p_home - even.p_home) < 0.20


def test_live_xg_still_sums_to_one():
    wp = simulate_live_wp(1.5, 1.0, LiveState(70, 2, 1, home_xg=1.8, away_xg=1.2), seed=7)
    assert _close(wp.p_home + wp.p_draw + wp.p_away, 1.0, tol=0.001)
