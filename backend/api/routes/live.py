"""Live-match endpoints — current state, swing-chart history, and SSE stream.

The SSE stream reads tail-of-history from `LiveWpHistory` every 5 seconds and emits
new ticks to the browser. Closes when the match ends (status in FT/AET/PEN) and the
client has caught up. Includes 15-second keep-alive pings to defeat proxy timeouts.
"""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from backend.db.session import get_db, SessionLocal
from backend.db.models import LiveMatchState, LiveWpHistory, Match, Team

router = APIRouter()


def _state_dict(lms: LiveMatchState) -> dict:
    return {
        "match_id": lms.match_id,
        "status": lms.status,
        "elapsed_min": lms.elapsed_min,
        "home_score": lms.home_score,
        "away_score": lms.away_score,
        "home_red_cards": lms.home_red_cards,
        "away_red_cards": lms.away_red_cards,
        "home_possession": lms.home_possession,
        "away_possession": lms.away_possession,
        "home_shots": lms.home_shots,
        "away_shots": lms.away_shots,
        "home_shots_on_target": lms.home_shots_on_target,
        "away_shots_on_target": lms.away_shots_on_target,
        "home_xg": lms.home_xg,
        "away_xg": lms.away_xg,
        "updated_at": lms.updated_at.isoformat() if lms.updated_at else None,
    }


def _tick_dict(t: LiveWpHistory) -> dict:
    return {
        "id": t.id,
        "elapsed_min": t.elapsed_min,
        "p_home": t.p_home,
        "p_draw": t.p_draw,
        "p_away": t.p_away,
        "home_score": t.home_score,
        "away_score": t.away_score,
        "event_label": t.event_label,
    }


@router.get("/upcoming")
def upcoming_matches(n: int = 3, db: Session = Depends(get_db)):
    """Next few matches about to kick off. Excludes matches that are CURRENTLY
    live (LiveMatchState in an in-play status). Does NOT exclude pre-match rows
    seeded by the prefetcher (status NS) — those are still upcoming."""
    in_play_statuses = ["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]
    live_ids = {
        s.match_id
        for s in db.query(LiveMatchState.match_id)
        .filter(LiveMatchState.status.in_(in_play_statuses))
        .all()
    }
    matches = (
        db.query(Match)
        .filter(Match.status.in_(["upcoming", "in_play"]), ~Match.id.in_(live_ids))
        .order_by(Match.kickoff.asc())
        .limit(n)
        .all()
    )
    out = []
    for m in matches:
        home = db.query(Team).filter(Team.code == m.home_code).first()
        away = db.query(Team).filter(Team.code == m.away_code).first()
        if not home or not away:
            continue
        out.append({
            "id": m.id,
            "home_name": home.name,
            "away_name": away.name,
            "home_flag": home.flag_url,
            "away_flag": away.flag_url,
            "kickoff": m.kickoff.isoformat() if m.kickoff else None,
            "group": m.group,
            "matchday": m.matchday,
            "status": m.status,
        })
    return {"matches": out}


@router.get("/recent")
def recent_matches(n: int = 3, db: Session = Depends(get_db)):
    """Last few completed matches with scores. Drives the 'just finished' strip on /live."""
    matches = (
        db.query(Match)
        .filter(Match.status == "complete", Match.home_score.isnot(None))
        .order_by(Match.kickoff.desc())
        .limit(n)
        .all()
    )
    out = []
    for m in matches:
        home = db.query(Team).filter(Team.code == m.home_code).first()
        away = db.query(Team).filter(Team.code == m.away_code).first()
        if not home or not away:
            continue
        out.append({
            "id": m.id,
            "home_name": home.name,
            "away_name": away.name,
            "home_flag": home.flag_url,
            "away_flag": away.flag_url,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "group": m.group,
            "matchday": m.matchday,
        })
    return {"matches": out}


@router.get("/hub")
async def live_hub(db: Session = Depends(get_db)):
    """All currently live WC matches with latest state + WP tick + team names.

    Used by the /live page to show a scrollable feed of live match cards.
    """
    states = (
        db.query(LiveMatchState)
        .join(Match, LiveMatchState.match_id == Match.id)
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
        # Last tick for current WP
        last_tick = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.id.desc())
            .first()
        )
        # All ticks for mini sparkline
        ticks = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.elapsed_min.asc(), LiveWpHistory.id.asc())
            .all()
        )
        out.append({
            "match_id": s.match_id,
            "group": match.group,
            "matchday": match.matchday,
            "home_name": home.name if home else match.home_code.upper(),
            "away_name": away.name if away else match.away_code.upper(),
            "home_flag": home.flag_url if home else None,
            "away_flag": away.flag_url if away else None,
            "kickoff": match.kickoff.isoformat() if match.kickoff else None,
            "state": _state_dict(s),
            "wp": {
                "p_home": last_tick.p_home if last_tick else 0.333,
                "p_draw": last_tick.p_draw if last_tick else 0.333,
                "p_away": last_tick.p_away if last_tick else 0.333,
            } if last_tick else None,
            "sparkline": [
                {"e": t.elapsed_min, "h": round(t.p_home, 3), "a": round(t.p_away, 3)}
                for t in ticks[-20:]  # last 20 ticks is enough for a mini sparkline
            ],
        })
    # Sort: least remaining time first (most urgent match at top)
    out.sort(key=lambda x: -(x["state"]["elapsed_min"] or 0))
    return {"live_count": len(out), "matches": out}


@router.get("/match/{match_id}/live")
async def match_live_state(match_id: str, db: Session = Depends(get_db)):
    """Snapshot of the match's current live state + the full WP history so far.

    Used by the chart on first paint. After that the client switches to the SSE
    stream for incremental updates.
    """
    lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match_id).first()
    history = (
        db.query(LiveWpHistory)
        .filter(LiveWpHistory.match_id == match_id)
        .order_by(LiveWpHistory.elapsed_min.asc(), LiveWpHistory.id.asc())
        .all()
    )
    match = db.query(Match).filter(Match.id == match_id).first()
    return {
        "match_id": match_id,
        "state": _state_dict(lms) if lms else None,
        "history": [_tick_dict(t) for t in history],
        "match_status": match.status if match else None,
    }


@router.get("/match/{match_id}/stream")
async def match_live_stream(match_id: str, request: Request):
    """SSE stream: emit a `tick` event whenever LiveWpHistory grows, plus a `state`
    event whenever LiveMatchState updates. Closes when match status reaches FT and
    the client has caught up to the final tick.
    """
    async def generator():
        last_tick_id = 0
        last_state_ts = 0.0
        idle_seconds = 0
        # Hard upper bound — keep an SSE connection at most 3 hours; the typical
        # match is 90 minutes + halftime + extra, but we don't want a leaked client
        # holding forever.
        while idle_seconds < 3 * 60 * 60:
            if await request.is_disconnected():
                return

            db = SessionLocal()
            try:
                # New ticks?
                new_ticks = (
                    db.query(LiveWpHistory)
                    .filter(LiveWpHistory.match_id == match_id)
                    .filter(LiveWpHistory.id > last_tick_id)
                    .order_by(LiveWpHistory.id.asc())
                    .all()
                )
                for t in new_ticks:
                    yield {"event": "tick", "data": json.dumps(_tick_dict(t))}
                    last_tick_id = t.id

                # State changed?
                lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match_id).first()
                if lms and lms.updated_at:
                    ts = lms.updated_at.timestamp()
                    if ts > last_state_ts:
                        yield {"event": "state", "data": json.dumps(_state_dict(lms))}
                        last_state_ts = ts

                # End condition: match is FT and we've sent the last tick
                if lms and lms.status in ("FT", "AET", "PEN") and new_ticks == []:
                    yield {"event": "ended", "data": json.dumps({"status": lms.status})}
                    return
            finally:
                db.close()

            await asyncio.sleep(5.0)
            idle_seconds += 5

    # ping=15: keep-alive comment every 15s of silence to defeat Cloudflare/nginx idle timeouts.
    return EventSourceResponse(generator(), ping=15)
