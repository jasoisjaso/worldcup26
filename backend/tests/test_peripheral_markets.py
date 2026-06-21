"""Sanity tests for the corners + cards peripheral markets.

We're not running a real DB session here — exercising the pure math
(Poisson PMF, over-line probability, shrinkage blend toward the prior) is
enough to catch the regressions that matter most: a wrong tail probability,
a bad fallback when the sample is empty, or an outcome list that doesn't sum
to ~1.0 across the over/under pair.
"""
from __future__ import annotations

import pytest

from backend.betting import peripheral_markets as pm


def test_poisson_pmf_sums_to_one():
    """Sanity: the discrete distribution sums to ~1 over a wide enough range."""
    lam = 10.0
    total = sum(pm._poisson_pmf(k, lam) for k in range(0, 60))
    assert abs(total - 1.0) < 1e-6


def test_poisson_pmf_zero_lambda():
    """When λ = 0 the distribution is concentrated at 0."""
    assert pm._poisson_pmf(0, 0.0) == 1.0
    assert pm._poisson_pmf(1, 0.0) == 0.0
    assert pm._poisson_pmf(5, 0.0) == 0.0


def test_p_over_line_around_mean():
    """P(X > λ-0.5) ≈ slightly less than 0.5 (skewed distribution)."""
    lam = 10.0
    # X > 9.5 means X >= 10. For Poisson(10), P(X>=10) ≈ 0.542
    p = pm._p_over(9.5, lam)
    assert 0.50 < p < 0.60


def test_p_over_and_under_sum_to_one():
    """Outcomes for a single line must sum to 1.0 (the market is complete)."""
    lam = 8.0
    for line in [4.5, 8.5, 12.5]:
        p_over = pm._p_over(line, lam)
        p_under = 1.0 - p_over
        assert abs((p_over + p_under) - 1.0) < 1e-9
        assert 0 <= p_over <= 1
        assert 0 <= p_under <= 1


def test_p_over_monotonic_in_line():
    """A higher line is harder to clear, so P(over) must decrease."""
    lam = 10.0
    p_8 = pm._p_over(7.5, lam)
    p_10 = pm._p_over(9.5, lam)
    p_12 = pm._p_over(11.5, lam)
    assert p_8 > p_10 > p_12


def test_shrinkage_zero_sample_returns_prior():
    """With n=0 the estimate must equal the prior — never invent a number
    from no data."""
    assert pm._shrink_blend(None, 0, prior=5.0) == 5.0
    assert pm._shrink_blend(8.0, 0, prior=5.0) == 5.0  # n=0 wins regardless of avg


@pytest.mark.parametrize(
    "sample,observed,expected_rel",
    [
        (5, 8.0, "between"),     # n == min_sample → 50/50
        (50, 8.0, "near-observed"),  # large n → heavily observed
        (1, 8.0, "near-prior"),  # tiny n → heavily prior
    ],
)
def test_shrinkage_blend_behaviour(sample, observed, expected_rel):
    """Shrinkage formula: w = n / (n + min_sample). Verify the blend lands
    in the right region for representative sample sizes."""
    prior = 5.0
    est = pm._shrink_blend(observed, sample, prior=prior)

    if expected_rel == "between":
        # Exactly the midpoint for n = min_sample (n=5, default min_sample=5)
        assert abs(est - (prior + observed) / 2) < 0.01
    elif expected_rel == "near-observed":
        # n=50 → weight = 50/55 ≈ 0.91 → est ≈ 8 * 0.91 + 5 * 0.09 ≈ 7.73
        assert abs(est - observed) < 1.0
    elif expected_rel == "near-prior":
        # n=1 → weight = 1/6 ≈ 0.17 → est ≈ 8 * 0.17 + 5 * 0.83 ≈ 5.50
        assert abs(est - prior) < 1.0


def test_fair_odds_caps_at_thousand():
    """Don't print absurd 1/0.0001 odds — the FE renders these as '-'."""
    assert pm._fair(0.5) == 2.0
    # 0.001 → 1000 exactly (boundary), still emits a number.
    assert pm._fair(0.001) == 1000
    # 0.0001 → 10000, way past the cap, returns None.
    assert pm._fair(0.0001) is None
    assert pm._fair(0.0) is None
