"""Tests for the pick guardrails — the discipline layer that stops the model
smashing in implausible +EV bets and losing.

The headline regression test is the real loss that motivated this: a +68% EV
"Australia to beat USA" leg must be REJECTED, while a believable +6% solid
edge must still pass as a core (grade-counting) pick.
"""
from __future__ import annotations

from backend.betting.pick_guardrails import (
    CORE_MAX_RATIO,
    MAX_ABSOLUTE_EV,
    grade_pick,
    shrink_toward_market,
)


def test_australia_usa_plus68ev_is_rejected():
    """THE regression: model 0.45 vs sharp implied ~0.27 (~+68% EV) at decent
    sample must be rejected as implausible, not published."""
    g = grade_pick(
        model_prob=0.45,
        market_implied=0.27,
        book_odds=3.7,          # ~ +66% EV at 0.45
        sample=40,              # plenty of sample, so it's not shrink saving us
        sharp_implied=0.27,
    )
    assert g.tier == "reject", g.reason
    assert not g.counts_to_grade
    assert "implausible" in g.reason or "too far above" in g.reason


def test_believable_solid_edge_is_core():
    """A model rating a side ~10% above the market at a fair price is a core pick."""
    g = grade_pick(
        model_prob=0.55,
        market_implied=0.50,    # 1.10x — inside the believable band
        book_odds=2.0,
        sample=40,
    )
    assert g.tier == "core", g.reason
    assert g.counts_to_grade
    assert g.ev > 0


def test_speculative_band_excluded_from_grade():
    """An edge in the speculative band (under the EV cap) shows but doesn't grade."""
    g2 = grade_pick(
        model_prob=0.42,
        market_implied=0.30,    # 1.40x — speculative
        book_odds=2.5,          # 0.42*2.5-1 = 0.05 EV, under the 25% cap
        sample=40,
    )
    assert g2.tier == "speculative", g2.reason
    assert not g2.counts_to_grade


def test_absolute_ev_cap_rejects_even_modest_ratio():
    """A huge price can make EV blow the cap even at a modest ratio — reject."""
    g = grade_pick(
        model_prob=0.20,
        market_implied=0.16,    # 1.25x — inside core ratio band
        book_odds=7.0,          # 0.20*7-1 = 0.40 EV > 0.25 cap
        sample=40,
    )
    assert g.tier == "reject", g.reason
    assert g.ev > MAX_ABSOLUTE_EV


def test_thin_sample_shrinks_edge_away():
    """A big model edge on a thin sample gets shrunk toward the market, which
    can demote it out of a phantom 'core' edge."""
    # Raw model says 0.55 vs market 0.42 (1.31x — just over core). On a tiny
    # sample the shrink pulls it back toward 0.42, collapsing the edge.
    shrunk = shrink_toward_market(0.55, 0.42, sample=2)
    assert shrunk < 0.55, "thin sample must shrink the model prob toward market"
    assert abs(shrunk - 0.42) < abs(0.55 - 0.42), "shrunk value sits closer to market"


def test_full_sample_barely_shrinks():
    """With plenty of sample the model number is trusted (minimal shrink)."""
    shrunk = shrink_toward_market(0.55, 0.42, sample=200)
    assert abs(shrunk - 0.55) < 0.02


def test_longshot_price_demotes_to_speculative():
    """A believable ratio on a long price is variance-heavy → speculative, not core."""
    g = grade_pick(
        model_prob=0.12,
        market_implied=0.10,    # 1.20x — believable ratio
        book_odds=9.5,          # over CORE_MAX_ODDS; EV 0.12*9.5-1 = 0.14 < cap
        sample=40,
    )
    assert g.tier == "speculative", g.reason
    assert not g.counts_to_grade


def test_no_market_line_is_speculative_info_only():
    g = grade_pick(model_prob=0.40, market_implied=None, book_odds=None, sample=40)
    assert g.tier == "speculative"
    assert not g.counts_to_grade


def test_sharp_anchor_overrides_soft_book():
    """When a sharp line exists it's used as the edge anchor, not the soft book.
    A soft book that looks like value but the sharp says otherwise → not core."""
    g = grade_pick(
        model_prob=0.50,
        market_implied=0.42,    # soft book: looks like a 1.19x core edge
        book_odds=2.3,
        sample=40,
        sharp_implied=0.49,     # sharp says it's basically fair → ratio ~1.02
    )
    # Against the sharp anchor this is a tiny edge — still core but a small one,
    # and crucially NOT the inflated edge the soft book implied.
    assert g.market_implied == 0.49, "must anchor to the sharp line"
    assert g.tier == "core"
    assert g.model_prob / 0.49 < CORE_MAX_RATIO
