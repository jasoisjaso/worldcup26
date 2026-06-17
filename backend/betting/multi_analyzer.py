"""Custom multi analyzer: price an arbitrary user-built slip with correlation-aware
math and surface a single-leg optimizer suggestion.

Legs in DIFFERENT matches are independent and multiply. Legs in the SAME match are
CORRELATED and MUST NOT be multiplied; we read the joint straight off the Dixon-Coles
score grid for that match. This is the same path ``backend/betting/sgm.py`` uses for
the validated SGM tests, extended to multi-match slips.

Goal-bands (e.g. "2 to 4 goals") are not a single mask — they are the intersection of
an Over and an Under, which the joint helper already handles correctly when both legs
are present in the same match.

Everything here is a pure function of (lambdas per match, optional cached devig market
probs per match). The API route in ``betting.py`` fetches those inputs from the DB
and the odds cache, then calls into this module.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

from backend.betting.sgm import joint_probability_from_grid
from backend.models.poisson import build_score_matrix

DEFAULT_RHO = -0.13

# User-facing market keys -> the list of SGM mask keys that define the leg on the
# final-score grid. Composite entries (goal bands) expand into multiple masks; the
# joint helper intersects them naturally inside a single match.
MARKET_CATALOG: dict[str, tuple[list[str], str]] = {
    # 1X2
    "home_win":         (["home_win"],          "Home win"),
    "draw":             (["draw"],              "Draw"),
    "away_win":         (["away_win"],          "Away win"),
    # Double chance
    "1x":               (["1x"],                "Home or draw"),
    "x2":               (["x2"],                "Draw or away"),
    "12":               (["12"],                "Home or away"),
    # Totals
    "over_0_5":         (["over_0_5"],          "Over 0.5 goals"),
    "over_1_5":         (["over_1_5"],          "Over 1.5 goals"),
    "over_2_5":         (["over_2_5"],          "Over 2.5 goals"),
    "over_3_5":         (["over_3_5"],          "Over 3.5 goals"),
    "under_1_5":        (["under_1_5"],         "Under 1.5 goals"),
    "under_2_5":        (["under_2_5"],         "Under 2.5 goals"),
    "under_3_5":        (["under_3_5"],         "Under 3.5 goals"),
    "under_4_5":        (["under_4_5"],         "Under 4.5 goals"),
    # BTTS + clean sheets
    "btts":             (["btts"],              "Both teams to score"),
    "btts_no":          (["btts_no"],           "BTTS no"),
    "home_clean_sheet": (["home_clean_sheet"],  "Home clean sheet"),
    "away_clean_sheet": (["away_clean_sheet"],  "Away clean sheet"),
    # Team totals
    "home_over_0_5":    (["home_over_0_5"],     "Home over 0.5"),
    "home_over_1_5":    (["home_over_1_5"],     "Home over 1.5"),
    "away_over_0_5":    (["away_over_0_5"],     "Away over 0.5"),
    "away_over_1_5":    (["away_over_1_5"],     "Away over 1.5"),
    # Asian handicaps
    "ah_home_minus1":   (["ah_home_minus1"],    "Home -1"),
    "ah_home_plus1":    (["ah_home_plus1"],     "Home +1"),
    "ah_away_minus1":   (["ah_away_minus1"],    "Away -1"),
    "ah_away_plus1":    (["ah_away_plus1"],     "Away +1"),
    # Goal bands (intersection of an Over and an Under)
    "goals_1_to_3":     (["over_0_5", "under_3_5"], "1 to 3 goals"),
    "goals_2_to_4":     (["over_1_5", "under_4_5"], "2 to 4 goals"),
    "goals_3_to_5":     (["over_2_5", "under_5_5"], "3 to 5 goals"),
}

# Markets the in-match optimizer is allowed to swap a leg with. Curated so the search
# stays focused on outcomes a punter would actually consider, not 30 obscure lines.
SWAP_CANDIDATES: list[str] = [
    "home_win", "draw", "away_win",
    "1x", "x2", "12",
    "over_1_5", "over_2_5", "over_3_5",
    "under_2_5", "under_3_5", "under_4_5",
    "btts", "btts_no",
    "goals_1_to_3", "goals_2_to_4", "goals_3_to_5",
]

# Per-leg edge thresholds, used for the EDGE / NO-EDGE chip. A book price carries vig,
# so we don't claim an "edge" until the model's view beats the offered price by enough
# to be meaningfully above the de-vigged market. 5% is a conventional working line.
EDGE_EV_THRESHOLD = 0.05
NO_EDGE_BAND = 0.97  # model_prob / market_implied below this = anti-edge (model dislikes)


@dataclass
class Leg:
    match_id: str
    market: str
    book_price: float | None = None  # bookmaker price for this single leg, optional


def market_label(market: str) -> str:
    return MARKET_CATALOG.get(market, ([], market))[1]


def expand_market(market: str) -> list[str] | None:
    """The list of grid-mask keys for one user-facing market, or None if unknown."""
    entry = MARKET_CATALOG.get(market)
    return list(entry[0]) if entry else None


def _grid(lambda_home: float, lambda_away: float, rho: float = DEFAULT_RHO) -> np.ndarray:
    return build_score_matrix(lambda_home, lambda_away, max_goals=10, rho=rho)


def model_prob(market: str, lambda_home: float, lambda_away: float,
               rho: float = DEFAULT_RHO) -> float | None:
    """The model's marginal probability for one user-facing market (composite bands ok)."""
    masks = expand_market(market)
    if masks is None:
        return None
    g = _grid(lambda_home, lambda_away, rho)
    return joint_probability_from_grid(g, masks)


def same_match_joint(masks: Iterable[str], lambda_home: float, lambda_away: float,
                     rho: float = DEFAULT_RHO) -> float | None:
    g = _grid(lambda_home, lambda_away, rho)
    return joint_probability_from_grid(g, list(masks))


def _edge_flag(model_p: float | None, market_implied_p: float | None,
               book_price: float | None) -> tuple[str, float | None]:
    """('edge' | 'no_edge' | 'anti_edge' | 'unknown', per_leg_ev_if_priced).

    Per-leg EV is calculated against the user-supplied book price when given. The flag
    uses the de-vigged market_implied probability when available (sharper than 1/price).
    """
    if model_p is None:
        return "unknown", None
    if market_implied_p is None and book_price is None:
        return "unknown", None
    if book_price is not None:
        ev = model_p * book_price - 1.0
        # Prefer the devig comparison when we have it; otherwise use the EV threshold.
        if market_implied_p is not None:
            ratio = model_p / market_implied_p if market_implied_p > 0 else 1.0
            if ratio < NO_EDGE_BAND:
                return "anti_edge", round(ev, 4)
            if ev >= EDGE_EV_THRESHOLD:
                return "edge", round(ev, 4)
            return "no_edge", round(ev, 4)
        return ("edge" if ev >= EDGE_EV_THRESHOLD else "no_edge"), round(ev, 4)
    # No book price but a devig market is known
    ratio = model_p / market_implied_p if market_implied_p > 0 else 1.0
    if ratio >= 1.08:
        return "edge", None
    if ratio < NO_EDGE_BAND:
        return "anti_edge", None
    return "no_edge", None


def _price_slip(
    legs: list[Leg],
    lambdas_by_match: dict[str, tuple[float, float]],
    rho: float = DEFAULT_RHO,
) -> tuple[float | None, list[dict], list[str]]:
    """Return (combined_prob, per_match_breakdown, warnings).

    Combined prob = product of (same-match joint from grid) across matches. Returns
    None if any leg's market is not grid-priceable (so the caller can flag it rather
    than silently misprice).
    """
    warnings: list[str] = []
    by_match: dict[str, list[Leg]] = {}
    for leg in legs:
        by_match.setdefault(leg.match_id, []).append(leg)

    per_match: list[dict] = []
    combined = 1.0
    for mid, mlegs in by_match.items():
        lam = lambdas_by_match.get(mid)
        if lam is None:
            warnings.append(f"No lambdas for match {mid}; slip cannot be priced.")
            return None, per_match, warnings
        masks: list[str] = []
        unpriceable = False
        for leg in mlegs:
            exp = expand_market(leg.market)
            if exp is None:
                warnings.append(f"Unknown market '{leg.market}' on {mid}.")
                unpriceable = True
                break
            masks.extend(exp)
        if unpriceable:
            return None, per_match, warnings

        g = _grid(*lam, rho)
        # Same-match joint via grid intersection (the whole point of correlation).
        joint = joint_probability_from_grid(g, masks)
        # Naive within-match product: each leg's marginal, multiplied.
        naive_in_match = 1.0
        for leg in mlegs:
            exp = expand_market(leg.market) or []
            marg = joint_probability_from_grid(g, exp)
            naive_in_match *= marg if marg is not None else 0.0
        if joint is None:
            warnings.append(
                f"Leg on {mid} is not a function of the final score (e.g. half-time)."
            )
            return None, per_match, warnings

        per_match.append({
            "match_id": mid,
            "legs_in_match": len(mlegs),
            "joint_prob_from_grid": round(joint, 6),
            "naive_product_in_match": round(naive_in_match, 6),
            "correlation_effect": (round(joint / naive_in_match - 1.0, 4)
                                    if naive_in_match > 0 else 0.0),
        })
        combined *= joint

    return combined, per_match, warnings


def analyze_multi(
    legs: list[Leg] | list[dict],
    lambdas_by_match: dict[str, tuple[float, float]],
    *,
    slip_book_price: float | None = None,
    devig_market_by_match: dict[str, dict[str, float]] | None = None,
    labels_by_match: dict[str, str] | None = None,
    rho: float = DEFAULT_RHO,
) -> dict:
    """Verdict on a user-built slip.

    - ``legs``: list of ``Leg`` or ``{match_id, market, book_price?}`` dicts.
    - ``lambdas_by_match``: ``{match_id: (lambda_home, lambda_away)}``.
    - ``slip_book_price``: bookmaker's price for the whole multi (decimal). If given,
      slip-level EV = combined_prob * price - 1.
    - ``devig_market_by_match``: optional Shin-devigged market probabilities per
      match (``{match_id: {market: prob}}``). Used to attribute per-leg edge against
      a sharp baseline rather than the raw 1/price (which still has vig in it).
    - ``labels_by_match``: optional "Home vs Away" labels for display.
    """
    norm_legs: list[Leg] = []
    for entry in legs:
        if isinstance(entry, Leg):
            norm_legs.append(entry)
        else:
            norm_legs.append(Leg(
                match_id=entry["match_id"],
                market=entry["market"],
                book_price=entry.get("book_price"),
            ))

    devig = devig_market_by_match or {}
    labels = labels_by_match or {}

    combined, per_match, warnings = _price_slip(norm_legs, lambdas_by_match, rho)

    # Per-leg attribution: model marginal, market_implied (devig), edge flag.
    legs_out: list[dict] = []
    leg_model_probs: list[float | None] = []
    leg_implieds: list[float | None] = []
    for leg in norm_legs:
        lam = lambdas_by_match.get(leg.match_id)
        m_p = model_prob(leg.market, *lam, rho=rho) if lam else None
        implied = devig.get(leg.match_id, {}).get(leg.market)
        flag, leg_ev = _edge_flag(m_p, implied, leg.book_price)
        leg_model_probs.append(m_p)
        leg_implieds.append(implied)
        legs_out.append({
            "match_id": leg.match_id,
            "match_label": labels.get(leg.match_id, leg.match_id),
            "market": leg.market,
            "label": market_label(leg.market),
            "model_prob": round(m_p, 4) if m_p is not None else None,
            "market_implied": round(implied, 4) if implied is not None else None,
            "book_price": leg.book_price,
            "ev_leg": leg_ev,
            "edge_flag": flag,
        })

    fair_odds = round(1.0 / combined, 2) if combined and combined > 0 else None
    naive_cross_match = 1.0
    for p in leg_model_probs:
        naive_cross_match *= p if p is not None else 0.0
    ev = round(combined * slip_book_price - 1.0, 4) if (combined and slip_book_price) else None

    return {
        "legs": legs_out,
        "per_match": per_match,
        "combined_probability": round(combined, 6) if combined is not None else None,
        "naive_product_all_legs": round(naive_cross_match, 6),
        "fair_combined_odds": fair_odds,
        "slip_book_price": slip_book_price,
        "ev": ev,
        "warnings": warnings,
    }


# --- Optimizer ---------------------------------------------------------------------

@dataclass
class _Candidate:
    kind: str               # "swap" | "drop" | "replace_with_value"
    new_legs: list[Leg]
    description: str
    extra: dict             # any kind-specific payload (e.g. dropped leg index)


def _score(analysis: dict, objective: str,
           devig_market_by_match: dict[str, dict[str, float]] | None) -> float:
    """The single number the optimizer maximizes.

    - "land": combined_probability (just lift the chance the slip lands)
    - "ev":   slip's edge ratio = combined_prob / product(per_leg_market_implied),
              which proxies the slip's true value-vs-market when book prices are
              missing for some legs (it falls back to model marginal for those).
    """
    p = analysis.get("combined_probability") or 0.0
    if objective == "land":
        return p
    # EV objective: edge ratio against the de-vigged market baseline.
    devig = devig_market_by_match or {}
    denom = 1.0
    has_market_data = False
    for leg in analysis.get("legs", []):
        mid, mkt = leg["match_id"], leg["market"]
        implied = devig.get(mid, {}).get(mkt)
        if implied and implied > 0:
            denom *= implied
            has_market_data = True
        else:
            # No market price for this leg -> use its own model marginal so it does
            # not bias the ratio. This means a leg with no market data contributes
            # ratio=1 to the slip edge.
            mp = leg.get("model_prob")
            denom *= mp if mp else 1.0
    if not has_market_data:
        return p  # nothing to grade against; fall back to "land"
    return p / denom if denom > 0 else 0.0


def _ev_at_same_vig(current: dict, alt: dict) -> float | None:
    """Project the alt slip's EV by assuming the bookmaker's multiplicative vig stays
    the same as the current slip's. Honest about the assumption; useful when the user
    hasn't entered a new bookmaker price for the alternative yet."""
    cur_book = current.get("slip_book_price")
    cur_fair = current.get("fair_combined_odds")
    alt_fair = alt.get("fair_combined_odds")
    alt_prob = alt.get("combined_probability")
    if not (cur_book and cur_fair and alt_fair and alt_prob):
        return None
    vig_factor = cur_book / cur_fair
    proj_book = alt_fair * vig_factor
    return round(alt_prob * proj_book - 1.0, 4)


def _candidates_for_swap(legs: list[Leg]) -> list[_Candidate]:
    out: list[_Candidate] = []
    for i, leg in enumerate(legs):
        for cand_market in SWAP_CANDIDATES:
            if cand_market == leg.market:
                continue
            new_legs = list(legs)
            new_legs[i] = Leg(match_id=leg.match_id, market=cand_market,
                              book_price=None)
            out.append(_Candidate(
                kind="swap",
                new_legs=new_legs,
                description=(
                    f"Swap leg {i+1} ({market_label(leg.market)}) "
                    f"on {leg.match_id} for {market_label(cand_market)}"
                ),
                extra={"leg_index": i, "from_market": leg.market,
                       "to_market": cand_market},
            ))
    return out


def _candidates_for_drop(legs: list[Leg]) -> list[_Candidate]:
    out: list[_Candidate] = []
    if len(legs) <= 2:
        return out  # already minimum
    for i in range(len(legs)):
        new_legs = [l for j, l in enumerate(legs) if j != i]
        out.append(_Candidate(
            kind="drop",
            new_legs=new_legs,
            description=f"Drop leg {i+1} ({market_label(legs[i].market)})",
            extra={"leg_index": i},
        ))
    return out


def optimize(
    legs: list[Leg] | list[dict],
    lambdas_by_match: dict[str, tuple[float, float]],
    *,
    objective: str = "ev",
    slip_book_price: float | None = None,
    devig_market_by_match: dict[str, dict[str, float]] | None = None,
    labels_by_match: dict[str, str] | None = None,
    value_picks: list[dict] | None = None,  # outside-the-slip alternatives
    rho: float = DEFAULT_RHO,
) -> dict | None:
    """Return the best single-leg change, or None if the slip is already the best
    expression of the model's view.

    Objectives:
    - "ev":   maximize the slip's per-leg edge ratio (model vs de-vigged market)
              with the slip's combined probability as a tiebreaker.
    - "land": maximize the slip's combined probability.
    """
    norm: list[Leg] = []
    for entry in legs:
        if isinstance(entry, Leg):
            norm.append(entry)
        else:
            norm.append(Leg(match_id=entry["match_id"], market=entry["market"],
                            book_price=entry.get("book_price")))

    current = analyze_multi(
        norm, lambdas_by_match,
        slip_book_price=slip_book_price,
        devig_market_by_match=devig_market_by_match,
        labels_by_match=labels_by_match, rho=rho,
    )
    cur_score = _score(current, objective, devig_market_by_match)

    candidates: list[_Candidate] = []
    candidates += _candidates_for_swap(norm)
    candidates += _candidates_for_drop(norm)

    # Outside-the-slip suggestion: if the user has no edge on any leg, point at the
    # best value bet on the slate as a replacement for the worst leg.
    if value_picks:
        # Sort value picks by per-leg edge ratio descending; first non-duplicate match
        # becomes the replacement candidate.
        ranked = sorted(
            value_picks,
            key=lambda v: (v.get("model_prob", 0) / v.get("market_implied", 1.0)
                           if v.get("market_implied") else v.get("model_prob", 0)),
            reverse=True,
        )
        used_matches = {l.match_id for l in norm}
        # Replace the lowest-edge-ratio leg with the top value pick.
        # Identify the lowest-edge leg.
        leg_edges = []
        for i, leg in enumerate(norm):
            implied = (devig_market_by_match or {}).get(leg.match_id, {}).get(leg.market)
            mp = model_prob(leg.market, *lambdas_by_match[leg.match_id], rho=rho) \
                 if leg.match_id in lambdas_by_match else None
            ratio = (mp / implied) if (mp and implied) else 1.0
            leg_edges.append((ratio, i))
        leg_edges.sort()
        worst_idx = leg_edges[0][1] if leg_edges else 0
        for vp in ranked[:8]:
            if vp["match_id"] in used_matches and vp["match_id"] != norm[worst_idx].match_id:
                continue
            new_legs = list(norm)
            new_legs[worst_idx] = Leg(
                match_id=vp["match_id"], market=vp["market"], book_price=None,
            )
            candidates.append(_Candidate(
                kind="replace_with_value",
                new_legs=new_legs,
                description=(
                    f"Replace leg {worst_idx+1} with the slate's top value pick: "
                    f"{vp.get('match_label', vp['match_id'])} – "
                    f"{vp.get('label', market_label(vp['market']))}"
                ),
                extra={"leg_index": worst_idx, "value_pick": vp},
            ))
            break

    best: tuple[float, _Candidate, dict] | None = None
    for cand in candidates:
        a = analyze_multi(
            cand.new_legs, lambdas_by_match,
            slip_book_price=None,  # don't carry forward; we project EV below
            devig_market_by_match=devig_market_by_match,
            labels_by_match=labels_by_match, rho=rho,
        )
        if a.get("combined_probability") is None:
            continue
        s = _score(a, objective, devig_market_by_match)
        if best is None or s > best[0]:
            best = (s, cand, a)

    if best is None or best[0] <= cur_score * 1.0001:
        # Already as good as it gets under this objective; the optimizer should say so
        # rather than invent a change.
        return {
            "kind": "already_optimal",
            "reason": (
                "No single-leg change improves the slip under the chosen objective. "
                "This is already the model's best expression for this set of matches."
            ),
            "before": {
                "combined_probability": current.get("combined_probability"),
                "fair_combined_odds": current.get("fair_combined_odds"),
                "ev": current.get("ev"),
            },
        }

    _, cand, alt = best
    proj_ev = _ev_at_same_vig(current, alt) if slip_book_price else None
    return {
        "kind": cand.kind,
        "reason": cand.description,
        "extra": cand.extra,
        "before": {
            "combined_probability": current.get("combined_probability"),
            "fair_combined_odds": current.get("fair_combined_odds"),
            "ev": current.get("ev"),
        },
        "after": {
            "combined_probability": alt.get("combined_probability"),
            "fair_combined_odds": alt.get("fair_combined_odds"),
            "ev": proj_ev,
            "ev_assumes_same_vig": proj_ev is not None,
        },
        "new_legs": [
            {"match_id": l.match_id, "market": l.market,
             "label": market_label(l.market)}
            for l in cand.new_legs
        ],
    }
