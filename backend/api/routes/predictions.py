from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.models.group_predictor import predict_group_match
from backend.models.prediction_inputs import assemble
from backend.betting.ev import calculate_ev
from backend.betting.market import blend_three_way, blend_two_way
from backend.data.fetchers.odds import get_odds_for_match
from backend.data.fetchers.sharp_odds import sharp_anchor_for as _sharp_anchor_for
from backend.data.fetchers.lineups import get_lineup_reason
from backend.data.fetchers.suspensions import get_suspension_why_factors

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

    # Single shared assembly — identical to what prediction_logger scores.
    ctx = await assemble(m, home, away, db)
    home_input = ctx["home_input"]
    away_input = ctx["away_input"]
    venue_context = ctx["venue_context"]
    mods = ctx["modifiers"]
    # locals reused by why-factors / payload context below
    rest_mults = mods["rest_multipliers"]
    travel_mults = mods["travel_multipliers"]
    h2h_mults = mods["h2h_multipliers"]
    wx_mults = mods["weather_multipliers"]
    lineup_mults = mods["lineup_multipliers"]
    xg_mults = mods["xg_multipliers"]
    sp_mults = ctx["sp_mults"]

    pred = predict_group_match(
        home_input, away_input,
        venue_context=venue_context, matchday=m.matchday, **mods,
    )

    live_odds = await get_odds_for_match(match_id)
    # Sharp anchor (Pinnacle) — used as the de-vig source when present, falling
    # back to soft books automatically. None when the SGO cache doesn't have
    # this fixture yet or the feature flag is off.
    sharp = _sharp_anchor_for(home.name, away.name)
    odds_source = (
        "sharp+live" if (sharp and live_odds)
        else "sharp" if sharp
        else "live" if live_odds
        else "estimated"
    )

    # Bookmaker blend: model + Shin-devigged market. 1X2 (3-way) and Over/Under 2.5 (2-way).
    home_win, draw, away_win = blend_three_way(
        pred.home_win, pred.draw, pred.away_win, live_odds,
        sharp_anchor=sharp,
    )
    over_2_5, under_2_5 = blend_two_way(
        pred.over_2_5, pred.under_2_5,
        live_odds.get("over_2_5") if live_odds else None,
        live_odds.get("under_2_5") if live_odds else None,
        sharp_over=sharp.get("over_2_5") if sharp else None,
        sharp_under=sharp.get("under_2_5") if sharp else None,
    )

    # our_prob = blended/calibrated probability shown to the user.
    # model_prob = the model's RAW independent opinion. Value/EV is measured on model_prob
    # vs the bookie line, so the value finder hunts genuine edges rather than agreeing with
    # the de-vigged market (which the blend has already moved toward).
    market_defs = [
        {"market": "home_win", "label": f"{home.name} Win", "our_prob": home_win, "model_prob": pred.home_win},
        {"market": "draw",     "label": "Draw",              "our_prob": draw,     "model_prob": pred.draw},
        {"market": "away_win", "label": f"{away.name} Win",  "our_prob": away_win, "model_prob": pred.away_win},
        {"market": "over_2_5", "label": "Over 2.5 Goals",    "our_prob": over_2_5, "model_prob": pred.over_2_5},
        {"market": "btts",     "label": "Both Teams Score",  "our_prob": pred.btts, "model_prob": pred.btts},
    ]
    markets = []
    for entry in market_defs:
        mkey = entry["market"]
        live = live_odds.get(mkey) if live_odds else None
        odds = live if live is not None else DEFAULT_ODDS.get(mkey, 2.0)
        ev = calculate_ev(entry["model_prob"], odds) if live is not None else 0.0
        markets.append({
            **entry,
            "bookmaker_odds": odds,
            "ev": round(ev, 4),
            "is_positive_ev": live is not None and ev > 0,
        })

    extra_why = list(get_suspension_why_factors(match_id, home.code, away.code))
    # Confirmed lineup absences
    if lineup_mults[0] < 0.97:
        reason = get_lineup_reason(home.code)
        label = f"Lineup confirmed: key player missing ({reason})" if reason else "Key player absent from confirmed lineup"
        extra_why.append({"label": label, "direction": "negative"})
    if lineup_mults[1] < 0.97:
        reason = get_lineup_reason(away.code)
        label = f"Opposition lineup confirmed: key player missing ({reason})" if reason else "Opposition key player absent from confirmed lineup"
        extra_why.append({"label": label, "direction": "positive"})
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
    # Club xG form + set pieces
    if xg_mults[0] > 1.03:
        extra_why.append({"label": "Squad in strong club-season form: attacking output above tournament average", "direction": "positive"})
    elif xg_mults[0] < 0.97:
        extra_why.append({"label": "Squad club-season form below tournament average", "direction": "negative"})
    if xg_mults[1] > 1.03:
        extra_why.append({"label": "Opposition squad in strong form this season", "direction": "negative"})
    elif xg_mults[1] < 0.97:
        extra_why.append({"label": "Opposition squad below-average club-season form", "direction": "positive"})
    if sp_mults[0] > 1.015:
        extra_why.append({"label": "Set piece edge: strong attacking threat vs weaker defending opponent", "direction": "positive"})
    elif sp_mults[1] > 1.015:
        extra_why.append({"label": "Opposition set piece advantage: dangerous from dead balls", "direction": "negative"})
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
        "over_2_5": over_2_5,
        "under_2_5": under_2_5,
        "btts": pred.btts,
        # raw model opinion (pre-market-blend) for value/edge calculations downstream
        "model_probs": {
            "home_win": pred.home_win, "draw": pred.draw, "away_win": pred.away_win,
            "over_2_5": pred.over_2_5, "under_2_5": pred.under_2_5, "btts": pred.btts,
        },
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
            "lineup": lineup_mults,
            "xg": xg_mults,
            "set_pieces": sp_mults,
        },
    }


@router.get("/{match_id}/prediction")
async def get_prediction(match_id: str, db: Session = Depends(get_db)):
    return await _build_prediction(match_id, db)


@router.get("/{match_id}/markets")
async def get_markets(match_id: str, db: Session = Depends(get_db)):
    """Full derived markets sheet (fair odds for ~30 markets) for one match, from the same
    context-adjusted lambdas as the headline prediction.

    Also appends peripheral markets (corners + cards) derived from harvested
    FixtureArchive averages. These are tagged `indicative: true` + carry a
    `confidence` field so the FE can render a "low sample" caveat — they are
    NOT pooled into the value-board EV gate (per project spec)."""
    from backend.betting.markets import derive_markets
    from backend.betting.peripheral_markets import derive_peripheral_markets
    from backend.betting.goalscorer_markets import derive_goalscorer_markets

    pred = await _build_prediction(match_id, db)
    sheet = derive_markets(pred["lambda_home"], pred["lambda_away"])

    m = db.get(Match, match_id)
    if m and m.home_code and m.away_code:
        # Peripheral (corners + yellow cards) — from FixtureArchive averages.
        peripheral = derive_peripheral_markets(m.home_code, m.away_code, db)
        sheet["groups"].extend(peripheral)
        # Goalscorer — position-based prior + recent-goal bias. Always
        # tagged indicative; never feeds the value-board EV gate.
        scorers = derive_goalscorer_markets(
            m.home_code, m.away_code,
            pred["lambda_home"], pred["lambda_away"],
            db,
        )
        sheet["groups"].extend(scorers)

    sheet["match_id"] = match_id
    return sheet
