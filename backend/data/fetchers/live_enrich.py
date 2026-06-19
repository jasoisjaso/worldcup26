"""Enriched data fetchers for live matches — events (goal scorers, cards), lineups,
and api-football's own AI predictions. All available on the pro tier we're paying for."""
from __future__ import annotations
import logging, os
from datetime import datetime, timedelta
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _KEY}

# Cache TTLs
_EVENTS_TTL = timedelta(seconds=60)
_PRED_TTL = timedelta(minutes=5)
_LINEUP_TTL = timedelta(minutes=30)

_cache_events: dict[int, tuple[list[dict], datetime]] = {}
_cache_preds: dict[int, tuple[dict, datetime]] = {}
_cache_lineups: dict[int, tuple[list[dict], datetime]] = {}


async def _get_fixture_id(match_code: str) -> Optional[int]:
    """Resolve a WC fixture's api-football id. The live poller already does this —
    this is a lightweight alternative for other code paths."""
    from backend.data.fetchers.live import _resolve_fixture_id
    return await _resolve_fixture_id(match_code)


async def get_live_events(api_fixture_id: int) -> list[dict]:
    """Goal scorers, card recipients, subs. Cached for 60s."""
    now = datetime.utcnow()
    cached = _cache_events.get(api_fixture_id)
    if cached and (now - cached[1]) < _EVENTS_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{_BASE}/fixtures/events", params={"fixture": api_fixture_id}, headers=_HEADERS)
            if r.status_code != 200:
                return []
            raw = r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("events fetch %s failed: %s", api_fixture_id, exc)
        return []

    out = []
    for e in raw:
        t = e.get("time", {}) or {}
        player = e.get("player", {}) or {}
        assist = e.get("assist", {}) or {}
        team = e.get("team", {}) or {}
        out.append({
            "elapsed": t.get("elapsed"),
            "extra": t.get("extra"),
            "type": e.get("type"),
            "detail": e.get("detail"),
            "player_name": player.get("name"),
            "player_id": player.get("id"),
            "assist_name": assist.get("name") or None,
            "team_name": team.get("name"),
            "team_id": team.get("id"),
        })
    _cache_events[api_fixture_id] = (out, now)
    return out


async def get_prediction(api_fixture_id: int) -> Optional[dict]:
    """api-football's own AI prediction. Cached for 5 min."""
    now = datetime.utcnow()
    cached = _cache_preds.get(api_fixture_id)
    if cached and (now - cached[1]) < _PRED_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{_BASE}/predictions", params={"fixture": api_fixture_id}, headers=_HEADERS)
            if r.status_code != 200:
                return None
            rows = r.json().get("response", [])
            if not rows:
                return None
            raw = rows[0]
    except Exception as exc:
        logger.warning("predictions fetch %s failed: %s", api_fixture_id, exc)
        return None

    pred = raw.get("predictions", {}) or {}
    pct = pred.get("percent", {}) or {}
    comp = raw.get("comparison", {}) or {}
    out = {
        "winner_name": (pred.get("winner") or {}).get("name"),
        "winner_comment": (pred.get("winner") or {}).get("comment"),
        "win_or_draw": pred.get("win_or_draw"),
        "advice": pred.get("advice"),
        "pct_home": pct.get("home"),
        "pct_draw": pct.get("draw"),
        "pct_away": pct.get("away"),
        "form_home": (comp.get("form") or {}).get("home"),
        "form_away": (comp.get("form") or {}).get("away"),
        "h2h_home": (comp.get("h2h") or {}).get("home"),
        "h2h_away": (comp.get("h2h") or {}).get("away"),
    }
    _cache_preds[api_fixture_id] = (out, now)
    return out


async def get_lineups(api_fixture_id: int) -> list[dict]:
    """Starting XI + bench. Cached for 30 min."""
    now = datetime.utcnow()
    cached = _cache_lineups.get(api_fixture_id)
    if cached and (now - cached[1]) < _LINEUP_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(f"{_BASE}/fixtures/lineups", params={"fixture": api_fixture_id}, headers=_HEADERS)
            if r.status_code != 200:
                return []
            raw = r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("lineups fetch %s failed: %s", api_fixture_id, exc)
        return []

    out = []
    for t in raw:
        team_info = t.get("team", {}) or {}
        players = []
        for p in (t.get("startXI", []) or []):
            pl = p.get("player", {}) or {}
            players.append({"number": pl.get("number"), "name": pl.get("name"), "pos": pl.get("pos")})
        subs = []
        for p in (t.get("substitutes", []) or []):
            pl = p.get("player", {}) or {}
            subs.append({"number": pl.get("number"), "name": pl.get("name"), "pos": pl.get("pos")})
        formation = t.get("formation")
        out.append({
            "team_id": team_info.get("id"),
            "team_name": team_info.get("name"),
            "formation": formation,
            "starters": players,
            "substitutes": subs,
        })
    _cache_lineups[api_fixture_id] = (out, now)
    return out
