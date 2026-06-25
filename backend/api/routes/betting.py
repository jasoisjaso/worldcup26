from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.betting.kelly import quarter_kelly
from backend.betting.sgm import sgm_probability, joint_probability_from_grid
from backend.betting import multi_analyzer
from backend.betting.market import devig_shin
from backend.models.poisson import build_score_matrix
from backend.betting.ev import calculate_ev
from backend.betting.market import reliability_tier as _reliability, TIER_RANK as _TIER_RANK
from backend.betting.pick_guardrails import grade_pick as _grade_pick
from backend.api.routes.predictions import _build_prediction
from backend.data.fetchers.odds import (
    get_book_odds_for_match,
    get_odds_for_match,
    get_steam_signal,
    match_arbitrage,
)

router = APIRouter()

DEFAULT_ODDS = {
    "home_win": 2.00,
    "draw": 3.30,
    "away_win": 3.80,
    "over_2_5": 1.90,
    "btts": 1.85,
}


async def _all_value_markets(db: Session) -> list[dict]:
    matches = db.query(Match).filter(Match.status == "upcoming").order_by(Match.kickoff).all()
    results: list[dict] = []

    # DC fit sample per team — drives the thin-sample shrink in the guardrails.
    # A team with few fitted matches can't print a trustworthy big edge.
    from backend.models import dc_ratings as _dc
    try:
        _fitted_codes = _dc.get_fitted_codes()
    except Exception:
        _fitted_codes = set()

    from backend.data.fetchers.sharp_odds import sharp_anchor_for as _sharp_anchor_for

    for m in matches:
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if not home or not away:
            continue

        try:
            pred_dict = await _build_prediction(m.id, db)
        except Exception:
            continue

        # Sharp (Pinnacle) anchor for this fixture, if we have it — the truest
        # probability to measure edge against. None falls back to the soft book.
        sharp = _sharp_anchor_for(home.name, away.name)
        # Sample backing this match's numbers: min of the two teams' fit status.
        # A fitted team gets the full sample weight; an unfitted one is thin.
        both_fitted = (m.home_code in _fitted_codes) and (m.away_code in _fitted_codes)
        sample = 40 if both_fitted else 4

        for entry in pred_dict.get("markets", []):
            if not entry.get("is_positive_ev"):
                continue
            odds = entry.get("bookmaker_odds", 0)
            if not odds:
                continue
            # Edge is the model's RAW opinion vs the bookie line, so we don't shrink the
            # value by the market blend; our_prob is still the calibrated display number.
            model_prob = entry.get("model_prob", entry["our_prob"])
            mkey = entry["market"]
            # De-vigged soft-book implied (added to the prediction payload) and the
            # sharp implied for this market when available.
            soft_implied = entry.get("market_implied")
            sharp_implied = None
            if sharp:
                sk = {"home_win": "home_win", "draw": "draw", "away_win": "away_win",
                      "over_2_5": "over_2_5", "btts": "btts"}.get(mkey)
                if sk and sharp.get(sk):
                    sharp_implied = 1.0 / sharp[sk] if sharp[sk] > 1 else None

            # GUARDRAIL: classify into core / speculative / reject. Rejected picks
            # (implausible edge, longshot fantasy) never reach the board. This is
            # the fix for the +68% EV Australia-v-USA type loss.
            grade = _grade_pick(
                model_prob=model_prob,
                market_implied=soft_implied if soft_implied is not None else (1.0 / odds if odds > 1 else None),
                book_odds=odds,
                sample=sample,
                sharp_implied=sharp_implied,
            )
            if grade.tier == "reject":
                continue

            kelly = quarter_kelly(grade.model_prob, odds)
            steam = get_steam_signal(m.id, entry["market"], grade.model_prob)

            # Line-shopping: the best price across our books for this exact outcome, and
            # the EV you would actually get taking that price (>= the median EV).
            book = get_book_odds_for_match(m.id).get(entry["market"], {})
            best_price = book.get("best_price")
            best_book = book.get("best_book")
            ev_best = calculate_ev(grade.model_prob, best_price) if best_price else entry["ev"]

            results.append({
                "match_id": m.id,
                "match_label": f"{home.name} vs {away.name}",
                "group": m.group,
                "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                "matchday": m.matchday,
                "market": entry["market"],
                "label": entry["label"],
                "our_prob": entry["our_prob"],
                "model_prob": model_prob,
                "market_implied": grade.market_implied if grade.market_implied is not None else round(1.0 / odds, 4),
                "reliability": _reliability(grade.model_prob, odds),
                # Guardrail verdict — the FE splits core (counts to grade) from
                # speculative (user discretion, excluded from the grade).
                "grade": grade.tier,
                "grade_reason": grade.reason,
                "counts_to_grade": grade.counts_to_grade,
                "anchored_to_sharp": sharp_implied is not None,
                "bookmaker_odds": odds,
                "best_price": best_price,
                "best_book": best_book,
                "ev": grade.ev,
                "ev_best": ev_best,
                "kelly_pct": round(kelly * 100, 2),
                "is_positive_ev": True,
                "steam": steam,
                "home_code": m.home_code,
                "away_code": m.away_code,
            })

    # Core picks first, then speculative; within each, trustworthy tier then EV.
    results.sort(key=lambda x: (
        0 if x["counts_to_grade"] else 1,
        _TIER_RANK[x["reliability"]],
        -x["ev"],
    ))
    return results


@router.get("/value")
async def get_value(db: Session = Depends(get_db)):
    return await _all_value_markets(db)


@router.get("/arbs")
def get_arbs(db: Session = Depends(get_db)):
    """Cross-book sure-bets: markets where taking the best price of each outcome at a
    different bookmaker guarantees profit. Rare with three correlated books, so this is
    mostly empty — that is honest, not broken."""
    out: list[dict] = []
    matches = db.query(Match).filter(Match.status == "upcoming").order_by(Match.kickoff).all()
    for m in matches:
        book = get_book_odds_for_match(m.id)
        if not book:
            continue
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        label = f"{home.name} vs {away.name}" if home and away else m.id
        for market_name, keys in (
            ("Match result", ("home_win", "draw", "away_win")),
            ("Over / Under 2.5", ("over_2_5", "under_2_5")),
        ):
            arb = match_arbitrage(book, keys)
            if arb:
                out.append({
                    "match_id": m.id,
                    "match_label": label,
                    "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                    "market": market_name,
                    **arb,
                })
    out.sort(key=lambda x: -x["margin"])
    return out


@router.get("/acca")
async def get_acca(
    k: int = Query(5, ge=2, le=6, description="Max legs to consider before the objective's own cap"),
    matchday: int | None = None,
    objective: str = Query("balanced", description="solid | balanced | bold"),
    db: Session = Depends(get_db),
):
    """Model-built multis. Three objectives instead of one raw-EV greedy.

    - **solid:** max landing chance, capped at 3 legs, demands a high combined prob.
    - **balanced:** Kelly log-utility on the slip; dampens longshot bias naturally.
    - **bold:** EV but with a probability floor and Whelan size-rationality cap.

    Each slip is enumerated against per-objective per-leg caps, diversified across
    matchdays and market categories, combined probability via the correlation-aware
    grid path, and tagged with the Whelan geomean-per-leg-probability verdict so the
    user can see when a shorter slip would dominate long-run.
    """
    if objective not in {"solid", "balanced", "bold"}:
        objective = "balanced"

    value = await _all_value_markets(db)

    # Build the lambdas-by-match cache used by the correlation-aware combined
    # probability. We only need lambdas for matches that have at least one value pick.
    used_match_ids = {v["match_id"] for v in value}
    lambdas_by_match: dict[str, tuple[float, float]] = {}
    for mid in used_match_ids:
        try:
            pred = await _build_prediction(mid, db)
        except Exception:
            continue
        lh, la = pred.get("lambda_home"), pred.get("lambda_away")
        if lh is not None and la is not None:
            lambdas_by_match[mid] = (lh, la)

    picks = multi_analyzer.select_model_picks(
        value, lambdas_by_match,
        objective=objective, max_legs=k, matchday=matchday,
    )

    # Backwards-compat fall-through for the matchday filter: if the requested
    # matchday has no slip the picker can build, try the next one(s) so the page
    # never goes empty mid-tournament.
    if not picks and matchday is not None:
        for next_md in range(matchday + 1, 4):
            picks = multi_analyzer.select_model_picks(
                value, lambdas_by_match,
                objective=objective, max_legs=k, matchday=next_md,
            )
            if picks:
                break

    if not picks:
        picks = multi_analyzer.select_model_picks(
            value, lambdas_by_match, objective=objective, max_legs=k,
        )

    return picks


@router.post("/sgm")
async def build_sgm(match_id: str, markets: list[str], db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        return {"error": "Match not found"}

    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)
    if not home or not away:
        return {"error": "Team data missing"}

    try:
        pred_dict = await _build_prediction(match_id, db)
    except Exception:
        return {"error": "Prediction failed"}

    # Price the multi straight off the Dixon-Coles score grid: the true joint probability
    # of correlated within-match legs is the sum of grid cells satisfying all of them,
    # which captures the correlation exactly (a favourite winning lifts Over but suppresses
    # both-teams-to-score). Compare that to the naive independent product to show the edge.
    lh, la = pred_dict.get("lambda_home"), pred_dict.get("lambda_away")
    matrix = build_score_matrix(lh, la, rho=-0.13) if lh and la else None

    true_p = joint_probability_from_grid(matrix, markets) if matrix is not None else None

    if true_p is not None:
        marginals = [joint_probability_from_grid(matrix, [m]) for m in markets]
        naive = 1.0
        for mm in marginals:
            naive *= mm
        used_markets, method = list(markets), "grid"
    else:
        # Fallback: a leg is not a pure function of the final score (or no lambdas). Use the
        # heuristic on the markets we have a marginal for.
        mp = pred_dict.get("model_probs", pred_dict)
        selected = {k: mp[k] for k in markets if k in mp}
        if not selected:
            return {"error": "No valid markets selected"}
        naive = 1.0
        for p in selected.values():
            naive *= p
        true_p = sgm_probability([{"market": k, "probability": v} for k, v in selected.items()])
        used_markets, method = list(selected.keys()), "heuristic"

    fair_odds = round(1.0 / true_p, 2) if true_p and true_p > 0 else None
    corr = round(true_p / naive - 1.0, 4) if naive > 0 else 0.0

    return {
        "match_id": match_id,
        "markets": used_markets,
        # what the legs would be worth if they were independent (what books approximate)
        "naive_combined_prob": round(naive, 4),
        # the correlation-aware truth from the grid
        "true_combined_prob": round(true_p, 4),
        # +ve: the legs reinforce each other, so the fair multi is shorter than the product
        "correlation_effect": corr,
        # take the multi only if your bookmaker's bet-builder pays more than this
        "fair_combined_odds": fair_odds,
        "method": method,
    }


# --- Custom multi analyzer ("build your own") -----------------------------------------

class _LegIn(BaseModel):
    match_id: str
    market: str
    book_price: float | None = None  # bookmaker price for this single leg (optional)


class _AnalyzeIn(BaseModel):
    legs: list[_LegIn] = Field(default_factory=list)
    slip_book_price: float | None = None
    # "ev": maximize edge over de-vigged market; "land": maximize the slip's win chance
    objective: str = "ev"


def _devig_for_match(live: dict[str, float] | None) -> dict[str, float]:
    """De-vigged market probabilities for the markets we cache odds on (1X2 + OU 2.5),
    so the analyzer can attribute per-leg edge against a sharp baseline rather than the
    raw 1/price (which still carries the bookmaker margin)."""
    if not live:
        return {}
    out: dict[str, float] = {}
    triple = [live.get(k) for k in ("home_win", "draw", "away_win")]
    if all(triple):
        fair = devig_shin(triple)  # type: ignore[arg-type]
        if fair:
            out["home_win"], out["draw"], out["away_win"] = fair
            # Derived double-chance follows from the fair 1X2.
            out["1x"] = fair[0] + fair[1]
            out["x2"] = fair[1] + fair[2]
            out["12"] = fair[0] + fair[2]
    pair = [live.get("over_2_5"), live.get("under_2_5")]
    if all(pair):
        fair2 = devig_shin(pair)  # type: ignore[arg-type]
        if fair2:
            out["over_2_5"], out["under_2_5"] = fair2
    # BTTS yes/no: kept as raw 1/price if only one side is offered. devig if we have both
    # under any consistent naming.
    btts = live.get("btts")
    if btts and btts > 1.0:
        out["btts"] = 1.0 / btts  # vig-included; honest fallback
    return out


@router.post("/analyze-multi")
async def analyze_multi(payload: _AnalyzeIn = Body(...), db: Session = Depends(get_db)):
    """Price an arbitrary user-built multi correctly: cross-match legs multiply, same-
    match legs come off the Dixon-Coles score grid (true correlation, not the naive
    product). Returns the verdict + a single-leg optimizer suggestion under the chosen
    objective ("ev" or "land")."""
    if not payload.legs:
        return {"error": "Add at least one leg."}

    # Unique match IDs the slip touches; we build a single prediction per match.
    match_ids = sorted({leg.match_id for leg in payload.legs})

    lambdas_by_match: dict[str, tuple[float, float]] = {}
    labels_by_match: dict[str, str] = {}
    devig_by_match: dict[str, dict[str, float]] = {}
    missing: list[str] = []
    for mid in match_ids:
        m = db.get(Match, mid)
        if not m:
            missing.append(mid)
            continue
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if not home or not away:
            missing.append(mid)
            continue
        try:
            pred = await _build_prediction(mid, db)
        except Exception:
            missing.append(mid)
            continue
        lh, la = pred.get("lambda_home"), pred.get("lambda_away")
        if lh is None or la is None:
            missing.append(mid)
            continue
        lambdas_by_match[mid] = (lh, la)
        labels_by_match[mid] = f"{home.name} vs {away.name}"
        # No EXTRA odds-API call: read whatever odds the refresh job has cached.
        live = await get_odds_for_match(mid)
        devig_by_match[mid] = _devig_for_match(live)

    if missing:
        return {"error": f"Could not price {len(missing)} match(es): {', '.join(missing)}"}

    legs_in = [
        {"match_id": l.match_id, "market": l.market, "book_price": l.book_price}
        for l in payload.legs
    ]

    verdict = multi_analyzer.analyze_multi(
        legs_in, lambdas_by_match,
        slip_book_price=payload.slip_book_price,
        devig_market_by_match=devig_by_match,
        labels_by_match=labels_by_match,
    )

    # Slate-wide value picks (cached value board) as candidates for the
    # "swap weakest leg for the best value bet on the slate" suggestion.
    try:
        slate_value = await _all_value_markets(db)
    except Exception:
        slate_value = []

    suggestion = multi_analyzer.optimize(
        legs_in, lambdas_by_match,
        objective=payload.objective if payload.objective in {
            "solid", "balanced", "bold", "ev", "land",
        } else "balanced",
        slip_book_price=payload.slip_book_price,
        devig_market_by_match=devig_by_match,
        labels_by_match=labels_by_match,
        value_picks=slate_value,
    )

    verdict["suggestion"] = suggestion
    verdict["objective"] = payload.objective
    return verdict


class _BestPricesIn(BaseModel):
    match_ids: list[str] = Field(..., description="Match ids to fetch best book prices for")


@router.post("/multi/best-prices")
async def multi_best_prices(payload: _BestPricesIn = Body(...)):
    """Best available bookmaker price per market, per match. Used by the bet
    builder to suggest a fillable price next to each leg without forcing the
    user to type. Returns only the markets where we actually have odds — the
    Odds API only covers 1X2 / OU 2.5 / BTTS on the free tier."""
    out: dict[str, dict[str, dict]] = {}
    for mid in payload.match_ids[:32]:  # cap input size
        book_odds = get_book_odds_for_match(mid)
        # Compact: just market -> {price, book}, drop the {books: {...}} blob.
        compact = {}
        for market, entry in book_odds.items():
            compact[market] = {
                "best_price": entry.get("best_price"),
                "best_book": entry.get("best_book"),
            }
        if compact:
            out[mid] = compact
    return {"by_match": out}
