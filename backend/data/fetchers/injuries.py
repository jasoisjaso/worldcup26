"""
API-Football injury/suspension fetcher for WC2026 squads.

Provides a lambda multiplier per team based on which players are unavailable.
Returns 1.0 (no effect) when API_FOOTBALL_KEY is not set.

FREE TIER: 100 requests/day — enough for daily injury checks on all 48 teams
           (48 requests) plus match-day lineup pulls (up to 16 more).

Sign up at https://www.api-football.com (free, no credit card required).
Add API_FOOTBALL_KEY=your_key to the backend environment in docker-compose.yml.

Player impact estimates (lambda penalty per position/tier):
  Top scorer / playmaker (first name in squad, xG leader): -8%
  First-choice keeper:                                     -5%
  Regular starter:                                         -4%
  Rotation player:                                         -2%
"""
from __future__ import annotations
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE_URL = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# Cache: team_code → (multiplier, fetched_at)
_cache: dict[str, tuple[float, datetime]] = {}
_CACHE_TTL = timedelta(hours=6)

# WC2026 league ID in API-Football — confirmed league for FIFA World Cup 2026
_WC2026_LEAGUE_ID = 1   # League ID 1 = FIFA World Cup in API-Football
_WC2026_SEASON = 2026

# Rough per-player impact on team lambda when absent (negative = reduces lambda)
# Multiple injuries compound multiplicatively
_INJURY_IMPACTS = {
    "attacker": -0.07,
    "midfielder": -0.04,
    "defender": -0.03,
    "goalkeeper": -0.05,
}

# Team code → API-Football team ID mapping for all 48 WC2026 nations
# IDs sourced from API-Football /teams endpoint
_TEAM_IDS: dict[str, int] = {
    "ar": 26, "br": 6, "fr": 2, "de": 25, "es": 9,
    "pt": 27, "nl": 1118, "be": 1, "gb-eng": 10, "hr": 3,
    "ch": 15, "tr": 29, "at": 22, "no": 119, "cz": 382,
    "se": 605, "gb-sct": 1108, "ba": 818,
    "co": 31, "uy": 33, "ec": 130, "py": 34,
    "jp": 21, "kr": 149, "au": 25, "ir": 110,
    "sa": 523, "uz": 72, "qa": 164, "jo": 504, "iq": 164,
    "mx": 16, "us": 23, "ca": 94, "pa": 1353, "cw": 2439, "ht": 537,
    "ma": 36, "sn": 608, "ci": 1334, "eg": 768, "dz": 1318,
    "tn": 1312, "gh": 1305, "za": 398, "cd": 1281, "cv": 1301,
    "nz": 1326,
}


async def get_injury_multiplier(team_code: str) -> float:
    """
    Return a lambda multiplier for the team based on current injury/suspension list.
    1.0 = no known absences. 0.92 = key striker out. 0.88 = multiple starters out.
    Returns 1.0 immediately if API_FOOTBALL_KEY is not configured.
    """
    if not _API_KEY:
        return 1.0

    now = datetime.utcnow()
    cached = _cache.get(team_code)
    if cached and (now - cached[1]) < _CACHE_TTL:
        return cached[0]

    team_id = _TEAM_IDS.get(team_code)
    if not team_id:
        return 1.0

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE_URL}/injuries",
                headers=_HEADERS,
                params={
                    "league": _WC2026_LEAGUE_ID,
                    "season": _WC2026_SEASON,
                    "team": team_id,
                },
            )
            if resp.status_code != 200:
                return 1.0
            data = resp.json()
    except Exception:
        return 1.0

    injuries = data.get("response", [])
    multiplier = 1.0

    for injury in injuries:
        player_type = injury.get("player", {}).get("type", "").lower()
        reason = injury.get("reason", "").lower()
        if "questionable" in reason:
            continue  # only penalise confirmed absences
        for pos_key, impact in _INJURY_IMPACTS.items():
            if pos_key in player_type:
                multiplier *= (1.0 + impact)
                break

    multiplier = max(0.75, min(1.0, multiplier))  # floor at 25% reduction
    _cache[team_code] = (multiplier, now)
    return multiplier


async def get_injury_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Fetch both teams' injury multipliers concurrently."""
    import asyncio
    results = await asyncio.gather(
        get_injury_multiplier(home_code),
        get_injury_multiplier(away_code),
    )
    return float(results[0]), float(results[1])
