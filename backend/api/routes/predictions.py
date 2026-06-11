from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.models.group_predictor import predict_group_match, TeamInput
from backend.models.venue_advantage import get_venue_bonuses
from backend.models.match_context import (
    altitude_lambda_bonus,
    rest_days_multipliers,
    dead_rubber_multipliers as get_dead_rubber_mults,
    travel_multipliers as get_travel_mults,
)
from backend.betting.ev import calculate_ev
from backend.data.fetchers.results import get_recent_form
from backend.data.fetchers.odds import get_odds_for_match
from backend.data.fetchers.squad_values import get_squad_quality_multipliers
from backend.data.fetchers.injuries import get_injury_multipliers
from backend.data.fetchers.head_to_head import get_h2h_multipliers
from backend.data.fetchers.weather import get_weather_multipliers
from backend.data.overrides.loader import get_player_overrides

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
    home_override, away_override = get_player_overrides(home.code, away.code)

    home_input = TeamInput(
        elo=(home.elo or 1500.0) + venue_home_bonus + home_override,
        form=home_form,
        chance_quality=1.3,
        code=home.code,
    )
    away_input = TeamInput(
        elo=(away.elo or 1500.0) + venue_away_bonus + away_override,
        form=away_form,
        chance_quality=1.3,
        code=away.code,
    )

    venue_context = {
        "home_bonus": venue_home_bonus,
        "away_bonus": venue_away_bonus,
        "venue": m.venue or "",
    }

    # --- Context modifiers ---
    alt_bonus = altitude_lambda_bonus(m.venue or "")

    rest_mults = (1.0, 1.0)
    travel_mults = (1.0, 1.0)
    if m.kickoff:
        rest_mults = rest_days_multipliers(home.code, away.code, m.kickoff, db)
        travel_mults = get_travel_mults(home.code, away.code, m.venue or "", m.kickoff, db)

    dr_mults = get_dead_rubber_mults(
        home.code, away.code,
        m.matchday or 1,
        m.group or "",
        db,
    )

    sq_mults = get_squad_quality_multipliers(home.code, away.code)
    inj_mults = await get_injury_multipliers(home.code, away.code)
    h2h_mults = await get_h2h_multipliers(home.code, away.code)
    wx_mults = await get_weather_multipliers(home.code, away.code, m.venue or "", m.kickoff)

    pred = predict_group_match(
        home_input,
        away_input,
        venue_context=venue_context,
        matchday=m.matchday,
        altitude_bonus=alt_bonus,
        rest_multipliers=rest_mults,
        dead_rubber_multipliers=dr_mults,
        squad_quality_multipliers=sq_mults,
        injury_multipliers=inj_mults,
        h2h_multipliers=h2h_mults,
        weather_multipliers=wx_mults,
        travel_multipliers=travel_mults,
    )

    live_odds = await get_odds_for_match(match_id)
    odds_source = "live" if live_odds else "estimated"

    # Bookmaker blend: 70% model / 30% vig-removed market for 3-way when odds are live
    home_win, draw, away_win = pred.home_win, pred.draw, pred.away_win
    if live_odds:
        raw_h = live_odds.get("home_win")
        raw_d = live_odds.get("draw")
        raw_a = live_odds.get("away_win")
        if raw_h and raw_d and raw_a and raw_h > 1.01 and raw_d > 1.01 and raw_a > 1.01:
            imp_h, imp_d, imp_a = 1 / raw_h, 1 / raw_d, 1 / raw_a
            total_imp = imp_h + imp_d + imp_a
            fair_h = imp_h / total_imp
            fair_d = imp_d / total_imp
            fair_a = imp_a / total_imp
            bl_h = 0.70 * pred.home_win + 0.30 * fair_h
            bl_d = 0.70 * pred.draw    + 0.30 * fair_d
            bl_a = 0.70 * pred.away_win + 0.30 * fair_a
            total_bl = bl_h + bl_d + bl_a
            home_win = round(bl_h / total_bl, 4)
            draw     = round(bl_d / total_bl, 4)
            away_win = round(bl_a / total_bl, 4)

    market_defs = [
        {"market": "home_win", "label": f"{home.name} Win", "our_prob": home_win},
        {"market": "draw",     "label": "Draw",              "our_prob": draw},
        {"market": "away_win", "label": f"{away.name} Win",  "our_prob": away_win},
        {"market": "over_2_5", "label": "Over 2.5 Goals",    "our_prob": pred.over_2_5},
        {"market": "btts",     "label": "Both Teams Score",  "our_prob": pred.btts},
    ]
    markets = []
    for entry in market_defs:
        mkey = entry["market"]
        live = live_odds.get(mkey) if live_odds else None
        odds = live if live is not None else DEFAULT_ODDS.get(mkey, 2.0)
        ev = calculate_ev(entry["our_prob"], odds) if live is not None else 0.0
        markets.append({
            **entry,
            "bookmaker_odds": odds,
            "ev": round(ev, 4),
            "is_positive_ev": live is not None and ev > 0,
        })

    extra_why = []
    # H2H
    if h2h_mults[0] > 1.005:
        extra_why.append({"label": f"Head-to-head record favours this team (+{(h2h_mults[0]-1)*100:.1f}%)", "direction": "positive"})
    elif h2h_mults[0] < 0.995:
        extra_why.append({"label": f"Poor head-to-head record against this opponent ({(h2h_mults[0]-1)*100:.1f}%)", "direction": "negative"})
    # Weather
    if wx_mults[0] < 0.97:
        extra_why.append({"label": "Conditions disadvantage: climate mismatch or heavy rain", "direction": "negative"})
    elif wx_mults[1] < 0.97:
        extra_why.append({"label": "Weather favours this team: opposition poorly adapted", "direction": "positive"})
    # Travel
    if travel_mults[0] < 0.98:
        pct = int((1 - travel_mults[0]) * 100)
        extra_why.append({"label": f"Travel fatigue: long-haul venue change with short rest (-{pct}%)", "direction": "negative"})
    if travel_mults[1] < 0.98:
        pct = int((1 - travel_mults[1]) * 100)
        extra_why.append({"label": f"Opposition travel fatigue advantage (+{pct}%)", "direction": "positive"})

    return {
        "match_id": match_id,
        "home_win": home_win,
        "draw": draw,
        "away_win": away_win,
        "over_2_5": pred.over_2_5,
        "under_2_5": pred.under_2_5,
        "btts": pred.btts,
        "top_scores": pred.top_scores,
        "markets": markets,
        "why_factors": pred.why_factors + extra_why,
        "lambda_home": pred.lambda_home,
        "lambda_away": pred.lambda_away,
        "expected_corners": pred.expected_corners,
        "expected_cards": pred.expected_cards,
        "odds_source": odds_source,
        "context": {
            "h2h": h2h_mults,
            "weather": wx_mults,
            "travel": travel_mults,
            "rest": rest_mults,
        },
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
