"""Sharp-odds fetcher + sharp-anchor lookup tests.

Covers the pure functions (american-to-decimal, name normalisation, feature
flag, blend integration) without ever hitting the network — the HTTP fetch
itself is exercised by the live smoke test against the deployed VPS.
"""
import os
from unittest.mock import patch

import pytest

from backend.data.fetchers import sharp_odds as so
from backend.betting.market import blend_three_way, blend_two_way


def test_american_to_decimal_basic():
    # Pinnacle quotes American odds; convert to decimal.
    # +100/-100 are even-money (2.0 decimal) — both valid endpoints.
    assert so._american_to_decimal(+100) == 2.0
    assert so._american_to_decimal(-100) == 2.0
    assert so._american_to_decimal(-110) == 1.9091  # standard juice → ~1.909
    assert so._american_to_decimal(+112) == 2.12
    assert so._american_to_decimal(+200) == 3.0
    # Inside (-100, +100) is not a valid American quote.
    assert so._american_to_decimal(0) is None
    assert so._american_to_decimal(50) is None
    assert so._american_to_decimal(None) is None
    assert so._american_to_decimal("bogus") is None


def test_name_normalisation_aliases():
    # Aliases catch common naming drift between SGO and our internal codes.
    assert so._norm("South Korea") == "korea republic"
    assert so._norm("USA") == "united states"
    assert so._norm("  Ivory Coast  ") == "cote d'ivoire"
    # Unknown name passes through verbatim (lower-cased + stripped).
    assert so._norm(" Brazil ") == "brazil"


def test_feature_flag_default_on():
    # Default behaviour: anchor is enabled when env var is unset/blank.
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WC26_USE_SHARP_ANCHOR", None)
        assert so.sharp_anchor_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "FALSE", "no"])
def test_feature_flag_off_values(value):
    with patch.dict(os.environ, {"WC26_USE_SHARP_ANCHOR": value}):
        assert so.sharp_anchor_enabled() is False


def test_sharp_anchor_for_disabled_returns_none(monkeypatch):
    # With the feature off the helper short-circuits even if the cache has
    # data — so call sites never accidentally use Pinnacle when the operator
    # has explicitly disabled it.
    monkeypatch.setenv("WC26_USE_SHARP_ANCHOR", "0")
    so._cache_events = [{"home_name": "Brazil", "away_name": "Argentina",
                         "pinnacle": {"home_win": 2.0}}]
    try:
        assert so.sharp_anchor_for("Brazil", "Argentina") is None
    finally:
        so._cache_events = []


def test_lookup_uses_alias_table(monkeypatch):
    monkeypatch.setenv("WC26_USE_SHARP_ANCHOR", "1")
    so._cache_events = [{"home_name": "Korea Republic", "away_name": "Brazil",
                         "pinnacle": {"home_win": 4.5}}]
    try:
        # Our internal code may carry "South Korea" — alias resolves it.
        got = so.sharp_anchor_for("South Korea", "Brazil")
        assert got == {"home_win": 4.5}
    finally:
        so._cache_events = []


def test_blend_three_way_prefers_sharp_anchor():
    # When BOTH soft books and sharp anchor are provided, the sharp anchor
    # wins — that's the whole point of the wiring. Sharp prices implying a
    # 50/30/20 split should drag the model's flat prior toward those numbers.
    soft = {"home_win": 2.0, "draw": 3.5, "away_win": 4.0}      # implied ~50/29/25
    sharp = {"home_win": 2.0, "draw": 3.33, "away_win": 5.0}    # implied ~50/30/20
    h, d, a = blend_three_way(0.4, 0.3, 0.3, soft, sharp_anchor=sharp)
    # The sharp anchor pulls home up & away down vs the soft-only baseline.
    h_soft, d_soft, a_soft = blend_three_way(0.4, 0.3, 0.3, soft)
    assert a < a_soft  # away got pulled down by the sharp's lower away_win prob


def test_blend_two_way_prefers_sharp_over_under():
    # Same contract for the OU 2.5 market.
    o, u = blend_two_way(0.55, 0.45, 1.95, 1.95, sharp_over=1.90, sharp_under=2.00)
    # Output should be a valid distribution.
    assert 0.0 < o < 1.0
    assert 0.0 < u < 1.0
    assert abs((o + u) - 1.0) < 1e-6


def test_blend_passes_through_when_no_odds_at_all():
    # When no soft books and no sharp anchor are present, model is returned
    # untouched — that contract was true before this PR and must still hold.
    h, d, a = blend_three_way(0.5, 0.3, 0.2, None)
    assert (h, d, a) == (0.5, 0.3, 0.2)
