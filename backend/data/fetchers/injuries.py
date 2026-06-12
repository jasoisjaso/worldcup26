"""
API-Football injury and squad fetcher for WC2026.

Provides a lambda multiplier per team based on missing players.
Returns 1.0 (no effect) when API_FOOTBALL_KEY is not set.

FREE TIER: 100 requests/day.
  - Squads for all 48 teams: 48 requests/refresh (once per 24h)
  - Injury checks when WC2026 fixtures are in API-Football system

Set API_FOOTBALL_KEY in backend/.env on the VPS to enable.
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

_squad_cache: dict[str, tuple[list, datetime]] = {}   # team_code → (squad, fetched_at)
_injury_cache: dict[str, tuple[float, datetime]] = {}  # team_code → (multiplier, fetched_at)
_SQUAD_TTL = timedelta(hours=24)
_INJURY_TTL = timedelta(hours=4)

_WC2026_LEAGUE = 1
_WC2026_SEASON = 2026

# Verified API-Football team IDs for all 48 WC2026 nations
TEAM_IDS: dict[str, int] = {
    # UEFA (16)
    "fr": 2,      "es": 9,    "pt": 27,   "de": 25,   "nl": 1118,
    "be": 1,      "gb-eng": 10, "hr": 3,  "ch": 15,   "tr": 777,
    "at": 775,    "no": 1090, "cz": 770,  "gb-sct": 1108, "ba": 1113, "se": 5,
    # CONMEBOL (6)
    "ar": 26,     "br": 6,    "co": 8,    "uy": 7,    "ec": 2382, "py": 2380,
    # AFC (9)
    "jp": 12,     "ir": 22,   "kr": 17,   "au": 20,
    "sa": 23,     "uz": 1568, "qa": 1569, "jo": 1548, "iq": 1567,
    # CONCACAF (6)
    "mx": 16,     "us": 2384, "ca": 5529, "pa": 11,   "cw": 5530, "ht": 2386,
    # CAF (10)
    "ma": 31,     "sn": 13,   "ci": 1501, "eg": 32,   "dz": 1532,
    "tn": 28,     "cd": 1508, "za": 1531, "gh": 1504, "cv": 1533,
    # OFC (1)
    "nz": 4673,
}

# Lambda penalty per position when a player from the confirmed squad is unavailable
_POSITION_IMPACT = {
    "Attacker": -0.06,
    "Midfielder": -0.04,
    "Defender": -0.03,
    "Goalkeeper": -0.04,
}


async def _fetch_squad(team_code: str) -> list:
    """Fetch confirmed WC squad for a national team (26 players)."""
    team_id = TEAM_IDS.get(team_code)
    if not team_id:
        return []
    cached = _squad_cache.get(team_code)
    if cached and (datetime.utcnow() - cached[1]) < _SQUAD_TTL:
        return cached[0]
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/players/squads",
                headers=_HEADERS,
                params={"team": team_id},
            )
            if resp.status_code != 200:
                return []
            data = resp.json()
        squad = data.get("response", [{}])[0].get("players", [])
        _squad_cache[team_code] = (squad, datetime.utcnow())
        return squad
    except Exception:
        return []


async def _fetch_injuries_for_fixture(fixture_id: int) -> list:
    """Get injuries for a specific WC2026 fixture once fixtures are in the system."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/injuries",
                headers=_HEADERS,
                params={"fixture": fixture_id},
            )
            if resp.status_code != 200:
                return []
            return resp.json().get("response", [])
    except Exception:
        return []


async def get_upcoming_fixture_id(home_api_id: int, away_api_id: int) -> Optional[int]:
    """Find the upcoming WC2026 fixture ID for this matchup."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/fixtures",
                headers=_HEADERS,
                params={
                    "league": _WC2026_LEAGUE,
                    "season": _WC2026_SEASON,
                    "team": home_api_id,
                    "status": "NS",
                },
            )
            if resp.status_code != 200:
                return None
            fixtures = resp.json().get("response", [])
            for f in fixtures:
                teams = f.get("teams", {})
                if (teams.get("home", {}).get("id") == home_api_id and
                        teams.get("away", {}).get("id") == away_api_id):
                    return f["fixture"]["id"]
    except Exception:
        pass
    return None


async def get_squad_player_ids(team_code: str) -> set[int]:
    """Return the set of player IDs in the team's WC squad."""
    squad = await _fetch_squad(team_code)
    return {p["player"]["id"] for p in squad if p.get("player", {}).get("id")}


async def get_injury_multiplier(team_code: str) -> float:
    """
    Return a lambda multiplier based on current WC squad injuries/suspensions.
    1.0 = no known issues. 0.88 = multiple key starters unavailable.
    Returns 1.0 when API key is not set or no data is available.
    """
    if not _API_KEY:
        return 1.0

    cached = _injury_cache.get(team_code)
    if cached and (datetime.utcnow() - cached[1]) < _INJURY_TTL:
        return cached[0]

    team_id = TEAM_IDS.get(team_code)
    if not team_id:
        return 1.0

    # Attempt to find upcoming fixture and check its injury report
    # Falls back to 1.0 gracefully if WC2026 fixtures aren't in the system yet
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/injuries",
                headers=_HEADERS,
                params={
                    "league": _WC2026_LEAGUE,
                    "season": _WC2026_SEASON,
                    "team": team_id,
                },
            )
            if resp.status_code != 200:
                return 1.0
            injuries = resp.json().get("response", [])
    except Exception:
        return 1.0

    if not injuries:
        mult = 1.0
    else:
        mult = 1.0
        for inj in injuries:
            player = inj.get("player", {})
            reason = inj.get("reason", "").lower()
            if "questionable" in reason or "doubt" in reason:
                continue  # only confirmed absences
            pos = player.get("type", "")
            impact = _POSITION_IMPACT.get(pos, -0.02)
            mult *= (1.0 + impact)
        mult = max(0.75, min(1.0, mult))

    _injury_cache[team_code] = (mult, datetime.utcnow())
    return mult


async def get_injury_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Fetch both teams' injury multipliers concurrently."""
    import asyncio
    results = await asyncio.gather(
        get_injury_multiplier(home_code),
        get_injury_multiplier(away_code),
    )
    return float(results[0]), float(results[1])
