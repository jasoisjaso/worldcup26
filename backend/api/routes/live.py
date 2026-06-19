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
from backend.db.models import LiveMatchState, LiveWpHistory, Match

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
