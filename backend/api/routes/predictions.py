from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.models.group_predictor import predict_group_match, TeamInput
from backend.models.venue_advantage import get_venue_bonuses
from backend.betting.ev import calculate_ev
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


async def _build_prediction(match_id: str, db: Session) -> dict:
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")

    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)

    if not home or not away:
        raise HTTPException(status_code=404, detail="Team data missing")

    home_form, away_form = await _get_forms(home.code, away.code)

    venue_home_bonus, venue_away_bonus = get_venue_bonuses(
        home.code, away.code, m.venue or ""
    )

    home_input = TeamInput(
        elo=(home.elo or 1500.0) + venue_home_bonus,
        form=home_form,
        chance_quality=1.3,
        code=home.code,
    )
    away_input = TeamInput(
        elo=(away.elo or 1500.0) + venue_away_bonus,
        form=away_form,
        chance_quality=1.3,
        code=away.code,
    )

    venue_context = {
        "home_bonus": venue_home_bonus,
        "away_bonus": venue_away_bonus,
        "venue": m.venue or "",
    }

    pred = predict_group_match(home_input, away_input, venue_context=venue_context)

    live_odds = await get_odds_for_match(match_id)
    odds_source = "live" if live_odds else "estimated"

    market_defs = [
        {"market": "home_win", "label": f"{home.name} Win", "our_prob": pred.home_win},
        {"market": "draw",     "label": "Draw",              "our_prob": pred.draw},
        {"market": "away_win", "label": f"{away.name} Win",  "our_prob": pred.away_win},
        {"market": "over_2_5", "label": "Over 2.5 Goals",    "our_prob": pred.over_2_5},
        {"market": "btts",     "label": "Both Teams Score",  "our_prob": pred.btts},
    ]
    markets = []
    for entry in market_defs:
        mkey = entry["market"]
        live = live_odds.get(mkey)
        odds = live if live is not None else DEFAULT_ODDS.get(mkey, 2.0)
        ev = calculate_ev(entry["our_prob"], odds) if live is not None else 0.0
        markets.append({
            **entry,
            "bookmaker_odds": odds,
            "ev": round(ev, 4),
            "is_positive_ev": live is not None and ev > 0,
        })

    return {
        "match_id": match_id,
        "home_win": pred.home_win,
        "draw": pred.draw,
        "away_win": pred.away_win,
        "over_2_5": pred.over_2_5,
        "under_2_5": pred.under_2_5,
        "btts": pred.btts,
        "top_scores": pred.top_scores,
        "markets": markets,
        "why_factors": pred.why_factors,
        "lambda_home": pred.lambda_home,
        "lambda_away": pred.lambda_away,
        "odds_source": odds_source,
    }


async def _get_forms(home_code: str, away_code: str):
    import asyncio
    return await asyncio.gather(
        get_recent_form(home_code),
        get_recent_form(away_code),
    )


@router.get("/{match_id}/prediction")
async def get_prediction(match_id: str, db: Session = Depends(get_db)):
    return await _build_prediction(match_id, db)
