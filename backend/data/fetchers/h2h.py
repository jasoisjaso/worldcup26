"""Head-to-Head historical record between two teams.

Fetched on demand per match-page render (cached for 6h per team pair). Returns the
last N meetings with scoreline, date, and venue. Drives the "When these teams last
met" storytelling card on the match page.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.data.fetchers.injuries import TEAM_IDS

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

_TTL = timedelta(hours=6)
_cache: dict[tuple[str, str], tuple[dict, datetime]] = {}


async def get_h2h(home_code: str, away_code: str, last_n: int = 10) -> Optional[dict]:
    """Return last `last_n` meetings between the two teams as a structured dict, or
    None on failure. The order pair (home, away) is direction-insensitive — the API
    returns all H2H matches regardless of who's hosting.

    Cached for 6h per team pair.
    """
    if not _API_KEY:
        return None

    key = tuple(sorted([home_code, away_code]))
    cached = _cache.get(key)
    if cached and (datetime.utcnow() - cached[1]) < _TTL:
        return cached[0]

    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id or not away_id:
        return None

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                f"{_BASE}/fixtures/headtohead",
                params={"h2h": f"{home_id}-{away_id}", "last": last_n},
                headers=_HEADERS,
            )
            if r.status_code != 200:
                return None
            response = r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("h2h fetch failed: %s", exc)
        return None

    home_wins = away_wins = draws = 0
    matches = []
    for fx in response:
        fixture = fx.get("fixture") or {}
        teams = fx.get("teams") or {}
        goals = fx.get("goals") or {}
        league = fx.get("league") or {}

        fx_home = teams.get("home") or {}
        fx_away = teams.get("away") or {}
        gh = goals.get("home")
        ga = goals.get("away")
        if gh is None or ga is None:
            continue

        # Which side was OUR home team?
        # Track wins from our home_code's perspective.
        if fx_home.get("id") == home_id:
            our_for, our_against = gh, ga
        elif fx_away.get("id") == home_id:
            our_for, our_against = ga, gh
        else:
            continue

        if our_for > our_against:
            home_wins += 1
        elif our_for < our_against:
            away_wins += 1
        else:
            draws += 1

        matches.append({
            "date": fixture.get("date"),
            "competition": league.get("name"),
            "season": league.get("season"),
            "venue": (fixture.get("venue") or {}).get("name"),
            "home_name": fx_home.get("name"),
            "away_name": fx_away.get("name"),
            "home_goals": gh,
            "away_goals": ga,
        })

    result = {
        "home_code": home_code,
        "away_code": away_code,
        "total_meetings": len(matches),
        # Wins from OUR home team's perspective:
        "our_wins": home_wins,
        "opp_wins": away_wins,
        "draws": draws,
        "matches": matches,
    }
    _cache[key] = (result, datetime.utcnow())
    return result
