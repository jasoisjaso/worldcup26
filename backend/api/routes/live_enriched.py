"""Enriched live hub — events, api-football predictions, fair odds from our model."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team, OddsCache, LiveMatchState, LiveWpHistory
from backend.data.fetchers.live_enrich import get_live_events, get_prediction
from backend.betting.market import devig_shin

router = APIRouter()


def _fair_odds(db: Session, match_id: str) -> dict:
    """1X2 fair odds and implied probabilities from our devigged market consensus."""
    buckets = {"home_win": [], "draw": [], "away_win": []}
    for r in db.query(OddsCache).filter(OddsCache.match_id == match_id).all():
        if r.market in buckets:
            buckets[r.market].append(r.odds)

    fair = {"home": None, "draw": None, "away": None}
    probs = {"home": None, "draw": None, "away": None}

    if all(len(buckets[k]) >= 2 for k in buckets):
        avg_odds = [sum(buckets[m]) / len(buckets[m]) for m in ["home_win", "draw", "away_win"]]
        try:
            fp = devig_shin(avg_odds)
            if fp:
                for i, k in enumerate(["home", "draw", "away"]):
                    if fp[i] and fp[i] > 0:
                        fair[k] = round(fp[i], 2)
                        probs[k] = round(1.0 / fp[i], 3)
        except Exception:
            pass
    return {"fair_odds": fair, "implied_probs": probs}


async def _resolve_api_fixture_id(home_code: str, away_code: str) -> int | None:
    """Find the api-football fixture id for this WC matchup."""
    import httpx, os
    from backend.data.fetchers.live import TEAM_IDS
    key = os.getenv("API_FOOTBALL_KEY", "")
    hid = TEAM_IDS.get(home_code)
    aid = TEAM_IDS.get(away_code)
    if not hid or not aid:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as c:
            r = await c.get(
                "https://v3.football.api-sports.io/fixtures",
                params={"league": 1, "season": 2026, "live": "all"},
                headers={"x-apisports-key": key},
            )
            for fx in (r.json().get("response", []) or []):
                t = (fx.get("teams") or {})
                if (t.get("home") or {}).get("id") == hid and (t.get("away") or {}).get("id") == aid:
                    return (fx.get("fixture") or {}).get("id")
    except Exception:
        pass
    return None


@router.get("/hub/enriched")
async def live_hub_enriched(db: Session = Depends(get_db)):
    """All currently live WC matches with events + predictions + fair odds."""
    states = (
        db.query(LiveMatchState)
        .filter(LiveMatchState.status.in_(["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]))
        .all()
    )
    out = []
    for s in states:
        match = db.query(Match).filter(Match.id == s.match_id).first()
        if not match:
            continue
        home = db.query(Team).filter(Team.code == match.home_code).first()
        away = db.query(Team).filter(Team.code == match.away_code).first()

        last_tick = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.id.desc()).first()
        )
        ticks = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.elapsed_min.asc(), LiveWpHistory.id.asc()).all()
        )

        api_fid = await _resolve_api_fixture_id(match.home_code, match.away_code)
        events = await get_live_events(api_fid) if api_fid else []
        api_pred = await get_prediction(api_fid) if api_fid else None
        odds_data = _fair_odds(db, match.id)

        out.append({
            "match_id": s.match_id,
            "group": match.group,
            "matchday": match.matchday,
            "home_name": home.name if home else match.home_code.upper(),
            "away_name": away.name if away else match.away_code.upper(),
            "home_flag": home.flag_url if home else None,
            "away_flag": away.flag_url if away else None,
            "kickoff": match.kickoff.isoformat() if match.kickoff else None,
            "state": {
                "status": s.status, "elapsed_min": s.elapsed_min,
                "home_score": s.home_score, "away_score": s.away_score,
                "home_red_cards": s.home_red_cards, "away_red_cards": s.away_red_cards,
                "home_possession": s.home_possession, "away_possession": s.away_possession,
                "home_shots": s.home_shots, "away_shots": s.away_shots,
                "home_shots_on_target": s.home_shots_on_target, "away_shots_on_target": s.away_shots_on_target,
                "home_xg": s.home_xg, "away_xg": s.away_xg,
            },
            "wp": {
                "p_home": last_tick.p_home, "p_draw": last_tick.p_draw, "p_away": last_tick.p_away,
            } if last_tick else None,
            "sparkline": [
                {"e": t.elapsed_min, "h": round(t.p_home, 3), "a": round(t.p_away, 3)}
                for t in ticks[-30:]
            ],
            "events": events,
            "api_prediction": api_pred,
            "fair_odds": odds_data["fair_odds"],
            "implied_probs": odds_data["implied_probs"],
        })
    out.sort(key=lambda x: -(x["state"]["elapsed_min"] or 0))
    return {"live_count": len(out), "matches": out}
