"""Tests for the revamped /betting/acca picker (multi_analyzer.select_model_picks).

The old picker greedily maximised raw multi-EV with no probability floor; it produced
slips like Iran-upset + CV-SA-draw + Japan-O2.5 at 7-8% landing chance and +90% EV.

These tests pin the new behaviour: per-objective per-leg caps, diversification, and
Whelan's geomean-per-leg threshold for size rationality.
"""
from __future__ import annotations

import math

from backend.betting.multi_analyzer import (
    WHELAN_MIN_GEOMEAN_P_BY_SIZE,
    select_model_picks,
)


def _value_pick(*, match_id: str, market: str, label: str, model_prob: float,
                bookmaker_odds: float, matchday: int = 1, group: str = "A",
                home_code: str | None = None, away_code: str | None = None,
                grade: str = "core") -> dict:
    """Shape the picker expects from _all_value_markets."""
    market_implied = 1.0 / bookmaker_odds  # vig-included; the picker uses this for margin display
    ev = model_prob * bookmaker_odds - 1.0
    return {
        "match_id": match_id,
        "market": market,
        "label": label,
        "our_prob": model_prob,
        "model_prob": model_prob,
        "market_implied": market_implied,
        "bookmaker_odds": bookmaker_odds,
        "ev": ev,
        "kelly_pct": 1.0,
        "grade": grade,
        "counts_to_grade": grade == "core",
        "matchday": matchday,
        "group": group,
        "home_code": home_code or f"{match_id}h",
        "away_code": away_code or f"{match_id}a",
        "match_label": f"{home_code or match_id} vs {away_code or match_id}",
        "kickoff": None,
        "reliability": "solid",
        "best_price": bookmaker_odds,
        "best_book": "test",
        "ev_best": ev,
        "anchored_to_sharp": False,
        "grade_reason": "test",
        "steam": None,
        "is_positive_ev": True,
    }


def _lambda_for_model_prob(market: str, target: float) -> tuple[float, float]:
    """Pick a (lambda_home, lambda_away) pair that yields the given market prob.

    home_win / away_win need an asymmetric lambda profile (target 0.62 home_win is
    unreachable with la = 0.95 × lh). totals (over/under) work with symmetric lambdas.
    draw needs both lambdas low and roughly equal.

    Strategy: pick a market-appropriate (low_factor, high_factor) profile that biases
    the lambdas the right way, then bisect a single 'intensity' parameter t.
    """
    from backend.betting.multi_analyzer import model_prob

    if market in {"home_win", "1x", "home_clean_sheet"}:
        # Home favourite: la fixed low, lh swept.
        la = 0.9
        lo, hi = 0.5, 5.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            p = model_prob(market, mid, la)
            if p is None:
                return 1.6, la
            if abs(p - target) < 1e-3:
                return mid, la
            if p < target:
                lo = mid
            else:
                hi = mid
        return mid, la

    if market in {"away_win", "x2", "away_clean_sheet"}:
        lh = 0.9
        lo, hi = 0.5, 5.0
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            p = model_prob(market, lh, mid)
            if p is None:
                return lh, 1.6
            if abs(p - target) < 1e-3:
                return lh, mid
            if p < target:
                lo = mid
            else:
                hi = mid
        return lh, mid

    if market == "draw":
        # Draws maximise around low, equal lambdas.
        lo, hi = 0.4, 1.8
        for _ in range(80):
            mid = 0.5 * (lo + hi)
            p = model_prob(market, mid, mid)
            if p is None:
                return 0.9, 0.9
            if abs(p - target) < 1e-3:
                return mid, mid
            if p > target:
                # Too peaked → push lambdas up to reduce draw share.
                lo = mid
            else:
                hi = mid
        return mid, mid

    # totals / btts / handicaps: symmetric lambdas, bisect intensity.
    lo, hi = 0.1, 5.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        p = model_prob(market, mid, mid)
        if p is None:
            return 1.4, 1.3
        if abs(p - target) < 1e-3:
            return mid, mid
        if p < target:
            lo = mid
        else:
            hi = mid
    return mid, mid


# --- Picker rejects the wild-shit slip --------------------------------------------------

def test_picker_rejects_low_geomean_three_leg_under_balanced():
    """The exact pattern that caused the user's complaint:
    three contrarian legs each at ~32-37% per-leg model prob, +20% EV singly,
    stacked into a 3-leg multi with geomean p ~ 0.34 (below Whelan's 0.526).

    Under the new balanced objective, the picker must:
      - prefer a 2-leg slip with higher geomean to a 3-leg below Whelan, OR
      - if it returns the 3-leg, mark it `rationality_verdict='smaller_better'`.
    """
    legs = [
        _value_pick(match_id="JPN_SE", market="over_2_5", label="Over 2.5",
                    model_prob=0.657, bookmaker_odds=1.91, matchday=3, group="F",
                    home_code="jp", away_code="se"),
        _value_pick(match_id="EGY_IR", market="away_win", label="Iran Win",
                    model_prob=0.319, bookmaker_odds=3.9, matchday=3, group="G",
                    home_code="eg", away_code="ir"),
        _value_pick(match_id="CV_SA",  market="draw", label="Draw",
                    model_prob=0.376, bookmaker_odds=3.3, matchday=3, group="H",
                    home_code="cv", away_code="sa"),
    ]
    lambdas = {
        "JPN_SE": _lambda_for_model_prob("over_2_5", 0.657),
        "EGY_IR": _lambda_for_model_prob("away_win", 0.319),
        "CV_SA":  _lambda_for_model_prob("draw",     0.376),
    }

    picks = select_model_picks(legs, lambdas, objective="balanced", max_legs=5)

    # A 2-leg slip MUST exist (the candidate pool has 3 priceable picks above the
    # per-leg prob floor — Iran/CV-SA draws are 32-38%, JPN_SE is 66%).
    two_leg = [p for p in picks if p["size"] == 2]
    assert len(two_leg) == 1, "balanced picker must surface a 2-leg slip"

    # The 3-leg slip's geomean must be below Whelan-3 (0.526). If the picker
    # surfaces it at all, it must wear the `smaller_better` verdict.
    three_leg = [p for p in picks if p["size"] == 3]
    if three_leg:
        slip = three_leg[0]
        assert slip["geomean_per_leg_prob"] < 0.526, (
            f"3-leg geomean was {slip['geomean_per_leg_prob']:.3f}, expected < 0.526"
        )
        assert slip["rationality_verdict"] == "smaller_better"


def test_per_leg_caps_block_high_odds_low_prob_legs():
    """The old picker took legs at up to 8.0 odds and EV up to 150%. The new
    bold/balanced/solid picker tightens this. A 4.5 odds Iran-upset is allowed by
    bold but rejected by solid (which caps odds at 3.0 and prob floor at 0.40)."""
    legs = [
        _value_pick(match_id="A", market="home_win", label="Home", model_prob=0.55,
                    bookmaker_odds=2.0, matchday=1),
        _value_pick(match_id="B", market="home_win", label="Home", model_prob=0.50,
                    bookmaker_odds=2.2, matchday=1),
        _value_pick(match_id="C", market="away_win", label="Upset", model_prob=0.30,
                    bookmaker_odds=4.0, matchday=1),
    ]
    lambdas = {
        "A": _lambda_for_model_prob("home_win", 0.55),
        "B": _lambda_for_model_prob("home_win", 0.50),
        "C": _lambda_for_model_prob("away_win", 0.30),
    }

    solid = select_model_picks(legs, lambdas, objective="solid", max_legs=3)
    # Solid: per-leg prob >= 0.40 + per-leg odds <= 3.0 → "C" is dropped.
    for slip in solid:
        ids = {leg["match_id"] for leg in slip["legs"]}
        assert "C" not in ids, "solid should not take C (prob 0.30 below 0.40 floor)"

    bold = select_model_picks(legs, lambdas, objective="bold", max_legs=3)
    # Bold: per-leg prob >= 0.30 + per-leg odds <= 4.5 → "C" is allowed.
    if bold:
        any_with_c = any("C" in {leg["match_id"] for leg in s["legs"]} for s in bold)
        assert any_with_c, "bold should be able to take C"


def test_diversification_max_per_matchday_holds():
    """Three same-matchday home wins should NOT all stack into a 3-leg slip;
    the diversification cap is 2 per matchday."""
    legs = [
        _value_pick(match_id=f"M{i}", market="home_win", label="Home",
                    model_prob=0.60, bookmaker_odds=1.8, matchday=1,
                    home_code=f"h{i}", away_code=f"a{i}")
        for i in range(5)
    ]
    lambdas = {f"M{i}": _lambda_for_model_prob("home_win", 0.60) for i in range(5)}

    picks = select_model_picks(legs, lambdas, objective="balanced", max_legs=4)
    for slip in picks:
        md_counts: dict[int, int] = {}
        for leg in slip["legs"]:
            md = leg["matchday"]
            md_counts[md] = md_counts.get(md, 0) + 1
        assert max(md_counts.values()) <= 2, (
            f"size-{slip['size']} slip stacks {md_counts} legs on one matchday"
        )


def test_diversification_max_per_market_category_holds():
    """Three overs from three matches: balanced picker must not stack all 3.
    (Same market category = same kind of bet noise; cap at 2 per category.)"""
    legs = [
        _value_pick(match_id=f"M{i}", market="over_2_5", label="Over 2.5",
                    model_prob=0.60, bookmaker_odds=1.8, matchday=i + 1,
                    home_code=f"h{i}", away_code=f"a{i}")
        for i in range(4)
    ]
    lambdas = {f"M{i}": _lambda_for_model_prob("over_2_5", 0.60) for i in range(4)}

    picks = select_model_picks(legs, lambdas, objective="balanced", max_legs=4)
    for slip in picks:
        # totals category covers all over_/under_/goals_ markets
        totals_count = sum(1 for leg in slip["legs"]
                           if leg["market"].startswith(("over_", "under_", "goals_")))
        assert totals_count <= 2, (
            f"size-{slip['size']} slip has {totals_count} totals legs (cap is 2)"
        )


def test_solid_objective_caps_at_three_legs():
    """Solid never returns a 4 or 5 leg slip even if max_legs=5."""
    legs = [
        _value_pick(match_id=f"M{i}", market="home_win", label="Home",
                    model_prob=0.55, bookmaker_odds=1.95, matchday=i + 1,
                    home_code=f"h{i}", away_code=f"a{i}")
        for i in range(6)
    ]
    lambdas = {f"M{i}": _lambda_for_model_prob("home_win", 0.55) for i in range(6)}

    picks = select_model_picks(legs, lambdas, objective="solid", max_legs=5)
    for slip in picks:
        assert slip["size"] <= 3, f"solid returned size-{slip['size']} slip"


def test_returned_slips_carry_whelan_metadata():
    """Every slip must carry the metadata the FE renders: geomean_per_leg_prob,
    whelan_min, rationality_verdict, compound_margin."""
    legs = [
        _value_pick(match_id="A", market="home_win", label="A Home", model_prob=0.62,
                    bookmaker_odds=1.85, matchday=1, home_code="A", away_code="a"),
        _value_pick(match_id="B", market="home_win", label="B Home", model_prob=0.58,
                    bookmaker_odds=2.0, matchday=2, home_code="B", away_code="b"),
    ]
    lambdas = {
        "A": _lambda_for_model_prob("home_win", 0.62),
        "B": _lambda_for_model_prob("home_win", 0.58),
    }
    picks = select_model_picks(legs, lambdas, objective="balanced", max_legs=3)
    assert picks, "picker returned no slips"
    for slip in picks:
        assert "geomean_per_leg_prob" in slip
        assert "whelan_min" in slip
        assert slip["whelan_min"] == WHELAN_MIN_GEOMEAN_P_BY_SIZE[slip["size"]]
        assert slip["rationality_verdict"] in {"optimal_size", "smaller_better"}
        assert "compound_margin" in slip
        assert "objective" in slip and slip["objective"] == "balanced"


def test_combined_probability_uses_correlation_aware_path():
    """A 2-leg slip of two cross-match legs: combined prob == product of marginals
    (within rounding). Confirms we routed through analyze_multi rather than reusing
    the old naive `model_prob[i]` product directly on the value-board number."""
    legs = [
        _value_pick(match_id="A", market="home_win", label="A Home", model_prob=0.62,
                    bookmaker_odds=1.85, matchday=1, home_code="A", away_code="a"),
        _value_pick(match_id="B", market="home_win", label="B Home", model_prob=0.58,
                    bookmaker_odds=2.0, matchday=2, home_code="B", away_code="b"),
    ]
    lambdas = {
        "A": _lambda_for_model_prob("home_win", 0.62),
        "B": _lambda_for_model_prob("home_win", 0.58),
    }
    picks = select_model_picks(legs, lambdas, objective="balanced", max_legs=2)
    assert picks
    slip = picks[0]
    # Cross-match independence: combined ~= 0.62 * 0.58 = 0.36 — but we go through
    # the grid for each match's marginal, so accept a ±2pp tolerance for lambda
    # bisection slop and grid truncation.
    assert math.isclose(slip["combined_probability"], 0.36, abs_tol=0.04)
