from itertools import combinations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.betting.kelly import quarter_kelly, multi_kelly
from backend.betting.sgm import sgm_probability, joint_probability_from_grid
from backend.models.poisson import build_score_matrix
from backend.betting.ev import calculate_ev
from backend.betting.market import reliability_tier as _reliability, TIER_RANK as _TIER_RANK
from backend.api.routes.predictions import _build_prediction
from backend.data.fetchers.odds import get_steam_signal, get_book_odds_for_match, match_arbitrage

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

    for m in matches:
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if not home or not away:
            continue

        try:
            pred_dict = await _build_prediction(m.id, db)
        except Exception:
            continue

        for entry in pred_dict.get("markets", []):
            if not entry.get("is_positive_ev"):
                continue
            odds = entry.get("bookmaker_odds", 0)
            if not odds:
                continue
            # Edge is the model's RAW opinion vs the bookie line, so we don't shrink the
            # value by the market blend; our_prob is still the calibrated display number.
            model_prob = entry.get("model_prob", entry["our_prob"])
            kelly = quarter_kelly(model_prob, odds)
            steam = get_steam_signal(m.id, entry["market"], model_prob)

            # Line-shopping: the best price across our books for this exact outcome, and
            # the EV you would actually get taking that price (>= the median EV).
            book = get_book_odds_for_match(m.id).get(entry["market"], {})
            best_price = book.get("best_price")
            best_book = book.get("best_book")
            ev_best = calculate_ev(model_prob, best_price) if best_price else entry["ev"]

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
                "market_implied": round(1.0 / odds, 4),
                "reliability": _reliability(model_prob, odds),
                "bookmaker_odds": odds,
                "best_price": best_price,
                "best_book": best_book,
                "ev": entry["ev"],
                "ev_best": ev_best,
                "kelly_pct": round(kelly * 100, 2),
                "is_positive_ev": True,
                "steam": steam,
                "home_code": m.home_code,
                "away_code": m.away_code,
            })

    # Trustworthy edges first (solid > speculative > longshot), then by EV within each tier,
    # so the board no longer leads with implausible longshot "value".
    results.sort(key=lambda x: (_TIER_RANK[x["reliability"]], -x["ev"]))
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
    k: int = Query(4, ge=2, le=6, description="Max legs per multi; bounded to keep the combinatorial search cheap"),
    matchday: int | None = None,
    db: Session = Depends(get_db),
):
    value = await _all_value_markets(db)

    def _build_candidates(md_filter: int | None) -> list[dict]:
        # Multis only from believable legs — never longshot fantasies, since every leg
        # must win and one bad outlier sinks the whole multi.
        return [
            v for v in value
            if v["reliability"] in ("solid", "speculative")
            and v["ev"] <= 1.5 and v["bookmaker_odds"] <= 8.0
            and (md_filter is None or v.get("matchday") == md_filter)
        ][:25]

    candidates = _build_candidates(matchday)

    if not candidates and matchday is not None:
        for next_md in range(matchday + 1, 4):
            candidates = _build_candidates(next_md)
            if len(candidates) >= 2:
                break

    if not candidates:
        candidates = _build_candidates(None)

    if len(candidates) < 2:
        return []

    best_by_k: list[dict] = []
    max_k = min(k, len(candidates))

    for size in range(2, max_k + 1):
        best_ev = float("-inf")
        best_combo: list[dict] = []
        best_odds = 1.0
        best_prob = 1.0

        for combo in combinations(candidates, size):
            match_ids = {leg["match_id"] for leg in combo}
            if len(match_ids) < size:
                continue

            # Reject if the same benefitting team appears more than once
            seen_teams: set[str] = set()
            dupe = False
            for leg in combo:
                if leg["market"] == "home_win":
                    beneficiary: str | None = leg.get("home_code")
                elif leg["market"] == "away_win":
                    beneficiary = leg.get("away_code")
                else:
                    beneficiary = None  # draw bets don't lock a specific team
                if beneficiary:
                    if beneficiary in seen_teams:
                        dupe = True
                        break
                    seen_teams.add(beneficiary)
            if dupe:
                continue

            combined_prob = 1.0
            combined_odds = 1.0
            for leg in combo:
                # multi true-probability and EV use the model's own edge, not the
                # market-blended display number
                combined_prob *= leg.get("model_prob", leg["our_prob"])
                combined_odds *= leg["bookmaker_odds"]
            total_ev = (combined_prob * combined_odds) - 1.0
            if total_ev > best_ev:
                best_ev = total_ev
                best_combo = list(combo)
                best_odds = combined_odds
                best_prob = combined_prob

        if best_combo:
            best_by_k.append({
                "legs": best_combo,
                "combined_odds": round(best_odds, 2),
                "combined_probability": round(best_prob, 4),
                "ev": round(best_ev, 4),
                # Stake the multi as the single binary bet it is, on a heavier fractional
                # Kelly than singles since leg errors compound.
                "kelly_pct": round(multi_kelly(best_prob, best_odds, len(best_combo)) * 100, 2),
            })

    return best_by_k


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
