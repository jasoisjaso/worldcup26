from itertools import combinations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.models.group_predictor import predict_group_match, TeamInput
from backend.betting.ev import calculate_ev
from backend.betting.kelly import quarter_kelly
from backend.betting.sgm import sgm_probability
from backend.data.fetchers.results import get_recent_form
from backend.data.fetchers.odds import get_odds_for_match

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

        home_form = await get_recent_form(home.code)
        away_form = await get_recent_form(away.code)

        pred = predict_group_match(
            TeamInput(elo=home.elo or 1500.0, form=home_form, chance_quality=1.3, code=home.code),
            TeamInput(elo=away.elo or 1500.0, form=away_form, chance_quality=1.3, code=away.code),
        )

        live_odds = await get_odds_for_match(m.id)

        market_defs = [
            {"market": "home_win", "label": f"{home.name} Win", "our_prob": pred.home_win},
            {"market": "draw",     "label": "Draw",              "our_prob": pred.draw},
            {"market": "away_win", "label": f"{away.name} Win",  "our_prob": pred.away_win},
            {"market": "over_2_5", "label": "Over 2.5 Goals",    "our_prob": pred.over_2_5},
            {"market": "btts",     "label": "Both Teams Score",  "our_prob": pred.btts},
        ]

        for entry in market_defs:
            mkey = entry["market"]
            odds = live_odds.get(mkey)
            if odds is None:
                continue
            ev = calculate_ev(entry["our_prob"], odds)
            if ev > 0:
                kelly = quarter_kelly(entry["our_prob"], odds)
                results.append({
                    "match_id": m.id,
                    "match_label": f"{home.name} vs {away.name}",
                    "group": m.group,
                    "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                    "market": mkey,
                    "label": entry["label"],
                    "our_prob": entry["our_prob"],
                    "bookmaker_odds": odds,
                    "ev": round(ev, 4),
                    "kelly_pct": round(kelly * 100, 2),
                    "is_positive_ev": True,
                })

    results.sort(key=lambda x: x["ev"], reverse=True)
    return results


@router.get("/value")
async def get_value(db: Session = Depends(get_db)):
    return await _all_value_markets(db)


@router.get("/acca")
async def get_acca(k: int = 4, db: Session = Depends(get_db)):
    value = await _all_value_markets(db)
    # cap extreme EVs and longshot odds — keeps accas in realistic territory
    candidates = [
        v for v in value
        if v["ev"] <= 1.5 and v["bookmaker_odds"] <= 8.0
    ][:25]

    if len(candidates) < k:
        return []

    best_by_k: list[dict] = []
    for size in range(3, min(k + 1, len(candidates) + 1)):
        best_ev = float("-inf")
        best_combo: list[dict] = []
        best_odds = 1.0
        best_prob = 1.0

        # avoid same match appearing twice in a combo
        for combo in combinations(candidates, size):
            match_ids = {leg["match_id"] for leg in combo}
            if len(match_ids) < size:
                continue
            combined_prob = 1.0
            combined_odds = 1.0
            for leg in combo:
                combined_prob *= leg["our_prob"]
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

    home_form = await get_recent_form(home.code)
    away_form = await get_recent_form(away.code)
    pred = predict_group_match(
        TeamInput(elo=home.elo or 1500.0, form=home_form, chance_quality=1.3, code=home.code),
        TeamInput(elo=away.elo or 1500.0, form=away_form, chance_quality=1.3, code=away.code),
    )

    prob_map = {
        "home_win": pred.home_win,
        "draw": pred.draw,
        "away_win": pred.away_win,
        "over_2_5": pred.over_2_5,
        "btts": pred.btts,
    }

    selected = {k: prob_map[k] for k in markets if k in prob_map}
    if not selected:
        return {"error": "No valid markets selected"}

    raw_combined = 1.0
    for p in selected.values():
        raw_combined *= p

    sgm_legs = [{"market": k, "probability": v} for k, v in selected.items()]
    adjusted = sgm_probability(sgm_legs)

    combined_odds = 1.0
    for market in selected:
        combined_odds *= DEFAULT_ODDS.get(market, 2.0)

    implied_bookmaker = 1.0 / combined_odds if combined_odds > 0 else 0
    ev = calculate_ev(adjusted, combined_odds)

    return {
        "match_id": match_id,
        "markets": list(selected.keys()),
        "raw_combined_prob": round(raw_combined, 4),
        "adjusted_combined_prob": round(adjusted, 4),
        "combined_bookmaker_odds": round(combined_odds, 2),
        "bookmaker_implied_prob": round(implied_bookmaker, 4),
        "ev": round(ev, 4),
        "is_positive_ev": ev > 0,
    }
