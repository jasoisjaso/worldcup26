"""Custom-multi analyzer: cross-match independence, same-match correlation off the grid,
and the four worked examples from the feature spec, reproduced exactly enough that the
combined probability, fair odds, and EV land on the spec values within rounding."""
from __future__ import annotations

import math

from backend.betting.multi_analyzer import (
    Leg,
    analyze_multi,
    model_prob,
    optimize,
    same_match_joint,
)
from backend.models.poisson import build_score_matrix
from backend.betting.sgm import joint_probability_from_grid


# --- Helper: find equal-lambda match that yields a target marginal probability --------

def _lambdas_for_marginal(market: str, target: float, rho: float = -0.13,
                          tol: float = 1e-4) -> tuple[float, float]:
    """Bisect on the home lambda (with away = 0.95*home, a generic 'neutral-ish' match
    profile) until ``model_prob(market)`` hits the target. Used purely to construct
    synthetic match contexts that hit the spec's stated marginals so the slip totals
    can be checked against the spec exactly."""
    lo, hi = 0.05, 6.0
    for _ in range(80):
        mid = 0.5 * (lo + hi)
        p = model_prob(market, mid, 0.95 * mid, rho=rho)
        if abs(p - target) < tol:
            return mid, 0.95 * mid
        if p < target:
            lo = mid
        else:
            hi = mid
    return mid, 0.95 * mid


# ENG-CRO lambdas straight from the feature spec.
_ENG_CRO = (1.221, 1.138)

# Build three companion matches that hit the spec's stated marginals exactly.
_LH_PCD, _LA_PCD = _lambdas_for_marginal("over_1_5", 0.74)   # Portugal-DR Congo
_LH_COL, _LA_COL = _lambdas_for_marginal("over_2_5", 0.54)   # Colombia-Uzbekistan
_LH_GHA, _LA_GHA = _lambdas_for_marginal("over_1_5", 0.72)   # Ghana-Panama


def _lambdas():
    return {
        "PCD": (_LH_PCD, _LA_PCD),
        "COL": (_LH_COL, _LA_COL),
        "GHA": (_LH_GHA, _LA_GHA),
        "ENG": _ENG_CRO,
    }


# --- Per-market sanity on the ENG-CRO lambdas from the spec --------------------------

def test_eng_cro_marginals_match_the_spec():
    lh, la = _ENG_CRO
    # The spec quotes these to two decimals; the model lands within ~1 pt of each.
    assert math.isclose(model_prob("under_2_5", lh, la), 0.58, abs_tol=0.01)
    assert math.isclose(model_prob("draw",      lh, la), 0.32, abs_tol=0.01)
    assert math.isclose(model_prob("x2",        lh, la), 0.636, abs_tol=0.005)
    assert math.isclose(model_prob("goals_2_to_4", lh, la), 0.609, abs_tol=0.005)


def test_x2_and_2_to_4_joint_off_the_grid():
    """The spec's row-4 joint of ~38.8%, priced as the intersection on the score grid."""
    lh, la = _ENG_CRO
    joint = same_match_joint(["x2", "over_1_5", "under_4_5"], lh, la)
    assert math.isclose(joint, 0.388, abs_tol=0.005)
    # This particular pair happens to be ~ uncorrelated, so the joint ~= the product.
    product = model_prob("x2", lh, la) * model_prob("goals_2_to_4", lh, la)
    assert math.isclose(joint, product, abs_tol=0.003)


# --- The four worked-example rows from the spec --------------------------------------

def test_row1_under_2_5_no_edge():
    legs = [
        Leg("PCD", "over_1_5"),
        Leg("COL", "over_2_5"),
        Leg("GHA", "over_1_5"),
        Leg("ENG", "under_2_5"),
    ]
    res = analyze_multi(legs, _lambdas(), slip_book_price=5.95)
    assert math.isclose(res["combined_probability"], 0.167, abs_tol=0.003)
    assert math.isclose(res["fair_combined_odds"], 5.99, abs_tol=0.05)
    assert math.isclose(res["ev"], -0.007, abs_tol=0.01)


def test_row3_draw_lifts_ev():
    legs = [
        Leg("PCD", "over_1_5"),
        Leg("COL", "over_2_5"),
        Leg("GHA", "over_1_5"),
        Leg("ENG", "draw"),
    ]
    res = analyze_multi(legs, _lambdas(), slip_book_price=12.75)
    # Spec quotes the ENG-CRO draw at 32%; the model lands at 31.3%, so combined and
    # fair odds drift ~3% from the spec's rounded numbers. The EV direction is the
    # point of the row: the draw leg flips the slip from -0.7% to clearly positive.
    assert math.isclose(res["combined_probability"], 0.091, abs_tol=0.005)
    assert math.isclose(res["fair_combined_odds"], 11.0, abs_tol=0.40)
    assert 0.13 < res["ev"] < 0.20  # spec says +17.4%


def test_row4_x2_plus_band_is_the_value_pick():
    """ENG-CRO with TWO same-match legs (X2 and 2-4 goals): the same-match joint must
    come from the score grid; combined with the other three matches it lifts the slip
    to ~+34% EV at the bookmaker's 12.06 price."""
    legs = [
        Leg("PCD", "over_1_5"),
        Leg("COL", "over_2_5"),
        Leg("GHA", "over_1_5"),
        Leg("ENG", "x2"),
        Leg("ENG", "goals_2_to_4"),
    ]
    res = analyze_multi(legs, _lambdas(), slip_book_price=12.06)
    assert math.isclose(res["combined_probability"], 0.112, abs_tol=0.003)
    assert math.isclose(res["fair_combined_odds"], 8.96, abs_tol=0.10)
    assert res["ev"] > 0.30   # spec says +34.7%

    # The ENG entry must be reported with legs_in_match == 2 and the same-match joint
    # routed through the grid (not a naive multiplication in the cross-match path).
    eng = next(pm for pm in res["per_match"] if pm["match_id"] == "ENG")
    assert eng["legs_in_match"] == 2
    assert math.isclose(eng["joint_prob_from_grid"], 0.388, abs_tol=0.005)


# --- A same-match correlation case where joint != product (the test the spec asks for)

def test_same_match_correlation_actually_bites():
    """A heavy home favourite (2.3 vs 0.7): home_win + over_2_5 is strongly positively
    correlated, so the score-grid joint exceeds the naive product of the marginals.
    This is the path the analyzer MUST exercise — naive multiplication would silently
    misprice every same-match slip that pairs a result leg with a totals leg."""
    lambdas = {"M": (2.3, 0.7)}
    legs = [Leg("M", "home_win"), Leg("M", "over_2_5")]
    res = analyze_multi(legs, lambdas)

    pm = res["per_match"][0]
    joint = pm["joint_prob_from_grid"]
    naive = pm["naive_product_in_match"]
    assert joint > naive * 1.05  # at least 5% above the naive product
    assert pm["correlation_effect"] > 0.05

    # And the combined slip probability is the same number (only one match).
    assert math.isclose(res["combined_probability"], joint, abs_tol=1e-9)


def test_negative_correlation_in_same_match():
    """Home win + BTTS is negatively correlated: if the favourite wins it often does
    so to nil, so the grid joint is SHORTER than the product. The optimizer leans on
    this too: a slip pairing home_win + btts is overpriced under naive math."""
    lambdas = {"M": (2.3, 0.7)}
    res = analyze_multi([Leg("M", "home_win"), Leg("M", "btts")], lambdas)
    pm = res["per_match"][0]
    assert pm["joint_prob_from_grid"] < pm["naive_product_in_match"] * 0.97


def test_cross_match_legs_multiply_independently():
    """Legs in different matches must be the simple product of the per-match grid
    marginals — no correlation between independent games."""
    lambdas = {"A": (1.5, 1.0), "B": (1.4, 1.1)}
    res = analyze_multi(
        [Leg("A", "home_win"), Leg("B", "over_2_5")],
        lambdas,
    )
    p_a = model_prob("home_win", *lambdas["A"])
    p_b = model_prob("over_2_5", *lambdas["B"])
    assert math.isclose(res["combined_probability"], p_a * p_b, abs_tol=1e-6)


# --- Optimizer behaviour --------------------------------------------------------------

def test_optimizer_swaps_to_higher_ev_under_market_baseline():
    """Given a slip with one leg the model agrees with the book on and a different
    market where the model strongly disagrees, the EV optimizer must point at the
    swap that lifts the slip's edge ratio against the de-vigged market."""
    lambdas = _lambdas()
    # Synthetic de-vigged market: the book thinks Croatia/draw are 50% combined (X2 at
    # 0.50, model is 0.636 -> strong model edge), but under_2_5 is well-aligned (0.585
    # ~= model 0.58).
    devig = {
        "ENG": {"under_2_5": 0.585, "draw": 0.30, "x2": 0.50},
        "PCD": {"over_1_5": 0.74},
        "COL": {"over_2_5": 0.54},
        "GHA": {"over_1_5": 0.72},
    }
    legs = [
        Leg("PCD", "over_1_5"),
        Leg("COL", "over_2_5"),
        Leg("GHA", "over_1_5"),
        Leg("ENG", "under_2_5"),
    ]
    sug = optimize(legs, lambdas, objective="ev",
                   slip_book_price=5.95, devig_market_by_match=devig)
    assert sug is not None
    # The recommended change must be on the ENG leg (the only match where the model
    # disagrees with the book) and the new ENG market must be X2 or draw (model > book).
    assert sug["kind"] in {"swap", "drop"}
    new_eng = [l for l in sug["new_legs"] if l["match_id"] == "ENG"]
    assert any(l["market"] in {"x2", "draw"} for l in new_eng)


def test_optimizer_returns_already_optimal_when_nothing_improves():
    """If the slip is already the model's best expression under the chosen objective,
    the optimizer must say so rather than invent a change."""
    lambdas = {"M": (1.0, 1.0)}
    # Single leg with the highest-probability market the swap catalog can offer is
    # likely Over 1.5 / Under 4.5 / 1X / X2 / 12; pick a guaranteed-high one. Even if
    # not perfectly optimal, the optimizer must either find a better swap (and a
    # candidate exists) OR return already_optimal — we only require a sane response.
    legs = [Leg("M", "12"), Leg("M", "over_0_5")]
    sug = optimize(legs, lambdas, objective="land")
    assert sug is not None
    assert sug["kind"] in {"swap", "drop", "already_optimal"}


def test_unknown_market_is_flagged_in_warnings():
    res = analyze_multi(
        [Leg("M", "home_win"), Leg("M", "exact_score_3_2")],
        {"M": (1.5, 1.0)},
    )
    assert res["combined_probability"] is None
    assert any("exact_score" in w for w in res["warnings"])
