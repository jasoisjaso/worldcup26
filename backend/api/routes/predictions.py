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
from backend.data.fetchers.injuries import TEAM_IDS as _TEAM_IDS
from backend.data import computed_metrics as _cm

router = APIRouter()


def _harvested_team_snapshot(team_code: str, db: Session) -> dict | None:
    """Real harvested signals for one team, or None if we have no archived data.

    Pure DB reads from the harvest archive (FixtureArchive). Surfaced in the
    prediction `context` so the match card can show actual recent numbers —
    rolling xG and corners per match — not just model estimates.
    """
    api_id = _TEAM_IDS.get(team_code)
    if not api_id:
        return None
    snap: dict = {}
    xg_avg = None
    try:
        from backend.db.models import FixtureArchive
        rows = (
            db.query(FixtureArchive.xg)
            .filter(FixtureArchive.team_api_id == api_id)
            .filter(FixtureArchive.xg.isnot(None))
            .order_by(FixtureArchive.captured_at.desc())
            .limit(6)
            .all()
        )
        vals = [r[0] for r in rows if r[0] is not None]
        if vals:
            xg_avg = round(sum(vals) / len(vals), 2)
            snap["xg_per_match"] = xg_avg
            snap["xg_sample"] = len(vals)
    except Exception:
        pass
    try:
        cpm = _cm.team_corners_per_match(api_id, db, n=10)
        if cpm is not None:
            snap["corners_per_match"] = cpm
    except Exception:
        pass
    try:
        trend = _cm.team_xg_trend(api_id, db, n=5)
        if trend:
            snap["xg_trend"] = trend
    except Exception:
        pass
    return snap or None


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

    # Model-uncertainty signal: how far the ELO view and the DC fitted view
    # disagree for this matchup. Strong disagreement = genuinely less sure, a
    # free internal flag (no external data). None when DC has no fit for a team.
    from backend.models.elo_model import (
        elo_only_lambdas as _elo_only,
        dc_only_lambdas as _dc_only,
        uncertainty_flag as _uncertainty,
    )
    _elo_view = _elo_only(home.elo or 1500.0, away.elo or 1500.0, home.code, away.code)
    _dc_view = _dc_only(home.code, away.code)
    model_uncertainty = _uncertainty(_elo_view, _dc_view)

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
        {"market": "under_2_5", "label": "Under 2.5 Goals",  "our_prob": under_2_5, "model_prob": pred.under_2_5},
        {"market": "btts",     "label": "Both Teams Score",  "our_prob": pred.btts, "model_prob": pred.btts},
    ]
    # Widen the value scan beyond 1X2/O-U/BTTS to the lower-risk derived markets
    # people actually bet — Double Chance and Draw No Bet — composed off the same
    # Dixon-Coles grid. Each still passes the calibration guardrails downstream
    # (value board) so widening the surface doesn't loosen the discipline. Book
    # odds for these come from composing the 1X2 lines (the Odds API doesn't ship
    # them directly), mirroring multi_picker._resolve_leg_price.
    def _compose_dc_odds(*keys: str) -> float | None:
        prices = [live_odds.get(k) for k in keys] if live_odds else []
        if not prices or any(not p or p <= 1 for p in prices):
            return None
        return round(1.0 / sum(1.0 / p for p in prices), 3)  # fair mutually-exclusive composite

    composed_odds: dict[str, float | None] = {}
    if live_odds:
        composed_odds["1x"] = _compose_dc_odds("home_win", "draw")
        composed_odds["x2"] = _compose_dc_odds("draw", "away_win")
        composed_odds["12"] = _compose_dc_odds("home_win", "away_win")
    market_defs += [
        {"market": "1x", "label": f"{home.name} or Draw", "our_prob": pred.home_win + pred.draw,
         "model_prob": pred.home_win + pred.draw, "composed_odds": composed_odds.get("1x")},
        {"market": "x2", "label": f"Draw or {away.name}", "our_prob": pred.draw + pred.away_win,
         "model_prob": pred.draw + pred.away_win, "composed_odds": composed_odds.get("x2")},
        {"market": "12", "label": f"{home.name} or {away.name}", "our_prob": pred.home_win + pred.away_win,
         "model_prob": pred.home_win + pred.away_win, "composed_odds": composed_odds.get("12")},
    ]
    markets = []
    # De-vig the real book lines so the match-page "model vs market" view
    # compares against FAIR market probabilities (Shin), not the raw vigged
    # 1/odds. 1X2 share one de-vig; the 2-way O/U + BTTS each de-vig as a pair
    # with their complement. None when the line is a placeholder estimate.
    from backend.betting.market import devig_shin as _devig
    implied_map: dict[str, float] = {}
    if live_odds:
        three = _devig([
            live_odds.get("home_win"), live_odds.get("draw"), live_odds.get("away_win"),
        ]) if all(live_odds.get(k) for k in ("home_win", "draw", "away_win")) else None
        if three:
            implied_map["home_win"], implied_map["draw"], implied_map["away_win"] = three
            # Double-chance fair implied follows from the de-vigged 1X2.
            implied_map["1x"] = three[0] + three[1]
            implied_map["x2"] = three[1] + three[2]
            implied_map["12"] = three[0] + three[2]
        if live_odds.get("over_2_5") and live_odds.get("under_2_5"):
            ou = _devig([live_odds["over_2_5"], live_odds["under_2_5"]])
            if ou:
                implied_map["over_2_5"] = ou[0]
                implied_map["under_2_5"] = ou[1]
        if live_odds.get("btts") and live_odds.get("btts_no"):
            bt = _devig([live_odds["btts"], live_odds["btts_no"]])
            if bt:
                implied_map["btts"] = bt[0]
    for entry in market_defs:
        mkey = entry["market"]
        # Real book line if present, else a composed double-chance price, else
        # the placeholder default. Double-chance markets carry composed_odds.
        live = live_odds.get(mkey) if live_odds else None
        if live is None:
            live = entry.get("composed_odds")
        odds = live if live is not None else DEFAULT_ODDS.get(mkey, 2.0)
        ev = calculate_ev(entry["model_prob"], odds) if live is not None else 0.0
        market_entry = {k: v for k, v in entry.items() if k != "composed_odds"}
        markets.append({
            **market_entry,
            "bookmaker_odds": odds,
            # Fair (de-vigged) market probability for this market, or a single-
            # sided 1/odds fallback when we couldn't de-vig (missing complement).
            "market_implied": (
                round(implied_map[mkey], 4) if mkey in implied_map
                else (round(1.0 / odds, 4) if (live is not None and odds > 1) else None)
            ),
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
        # How much our two internal views (ELO vs DC) agree on this matchup:
        # "confident" | "moderate" | "uncertain" | null. A free model-uncertainty
        # read — when the views diverge we surface a "trust this less" caveat.
        "model_uncertainty": model_uncertainty,
        "context": {
            "h2h": h2h_mults,
            "weather": wx_mults,
            "travel": travel_mults,
            "rest": rest_mults,
            "lineup": lineup_mults,
            "xg": xg_mults,
            "set_pieces": sp_mults,
            # Real harvested per-team signals (None until a team has archived
            # fixtures). Lets the match card show actual recent numbers.
            "harvested": {
                "home": _harvested_team_snapshot(home.code, db),
                "away": _harvested_team_snapshot(away.code, db),
            },
        },
    }


@router.get("/{match_id}/prediction")
async def get_prediction(match_id: str, db: Session = Depends(get_db)):
    return await _build_prediction(match_id, db)


@router.get("/{match_id}/key-players")
def get_key_players(match_id: str, db: Session = Depends(get_db)):
    """Top 'players to watch' per side — outfielders ranked by goals/90 and
    assists/90 from the bundled per-90 club-season dataset (Rising Transfers,
    CC BY 4.0). Surfaces the names a punter cares about without leaving the
    match page.

    Pure DB read + in-memory name lookup; zero external API cost. Returns an
    empty list per side when we don't have any per-90 rows for the squad (early
    deploy, exotic federation, etc.).
    """
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.data.importers.wc2026_per90 import get_per90_for_name
    from backend.db.models import PlayerProfile

    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")

    def _players_for(team_code: str) -> list[dict]:
        api_id = TEAM_IDS.get(team_code)
        if not api_id:
            return []
        rows = (
            db.query(PlayerProfile)
            .filter(PlayerProfile.team_id == api_id)
            .all()
        )
        enriched: list[dict] = []
        for p in rows:
            pos = (p.position or "").lower()
            # Goalkeepers don't belong in an attacking "watch list".
            if "goalkeep" in pos or pos == "g":
                continue
            p90 = get_per90_for_name(p.name or "")
            if not p90:
                continue
            mins = p90.get("minutes") or 0
            # Floor on sample size so 80-minute cameos don't top the list.
            if mins < 600:
                continue
            g90 = p90.get("goals_per90")
            a90 = p90.get("assists_per90")
            if (g90 is None or g90 <= 0.0) and (a90 is None or a90 <= 0.0):
                continue
            enriched.append({
                "player_id": p.player_id,
                "name": p.name,
                "position": p.position or "Unknown",
                "photo_url": p.photo_url,
                "season": p90.get("season"),
                "minutes": mins,
                "goals_per90": g90,
                "assists_per90": a90,
                "shots_per90": p90.get("shots_per90"),
                "key_passes_per90": p90.get("key_passes_per90"),
                "rating": p90.get("rating"),
            })
        # Rank by attacking output (goals weighted heavier than assists), tie
        # break on rating then minutes. Top 3 — small enough to glance.
        def _score(row: dict) -> float:
            g = row.get("goals_per90") or 0.0
            a = row.get("assists_per90") or 0.0
            return g * 1.5 + a
        enriched.sort(
            key=lambda r: (_score(r), r.get("rating") or 0.0, r.get("minutes") or 0),
            reverse=True,
        )
        return enriched[:3]

    return {
        "match_id": match_id,
        "home": _players_for(m.home_code),
        "away": _players_for(m.away_code),
        "attribution": "Per-90 stats: Rising Transfers (risingtransfers.com), CC BY 4.0",
    }


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
