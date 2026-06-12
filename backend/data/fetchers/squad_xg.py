"""
Club-season form aggregator for WC2026 national squads.

Fetches top scorers (by goals+assists) from 8 major club leagues via
API-Football and cross-references each national team's WC squad to build
a "squad attack form" score.

A national team whose squad members had strong club seasons collectively
gets up to +4% lambda; a team with few top-scorer-caliber players gets
up to -4%.

Requests: ~10 per 24-hour cycle (one per league). Cached 24h.
Uses API_FOOTBALL_KEY from environment — returns (1.0, 1.0) if not set.
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timedelta

import httpx

from backend.data.fetchers.injuries import TEAM_IDS, get_squad_player_ids

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# Club leagues: id → name (8 major + 2 South American)
_CLUB_LEAGUES: dict[int, str] = {
    39:  "Premier League",
    140: "La Liga",
    78:  "Bundesliga",
    135: "Serie A",
    61:  "Ligue 1",
    88:  "Eredivisie",
    94:  "Primeira Liga",
    71:  "Brasileirao",
    128: "Argentine Liga",
    2:   "Champions League",
}

_CLUB_SEASON = 2024

# Goals+assists threshold to consider a player "in strong form" for this season
_IN_FORM_THRESHOLD = 12

# Expected count of in-form players per WC squad (league average)
_EXPECTED_COUNT = 2.0

# Max ±4% effect on lambda
_XG_SCALE = 0.04

_topscorer_cache: dict[int, tuple[dict[int, int], datetime]] = {}  # league_id -> ({pid: g+a}, ts)
_team_form_cache: dict[str, tuple[float, datetime]] = {}            # team_code -> (mult, ts)

_LEAGUE_TTL = timedelta(hours=24)
_FORM_TTL = timedelta(hours=24)


async def _fetch_top_scorers(league_id: int) -> dict[int, int]:
    """
    Fetch top 20 scorers for a league and return {player_id: goals+assists}.
    Falls back to {} on any error.
    """
    cached = _topscorer_cache.get(league_id)
    if cached and (datetime.utcnow() - cached[1]) < _LEAGUE_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(
                f"{_BASE}/players/topscorers",
                headers=_HEADERS,
                params={"league": league_id, "season": _CLUB_SEASON},
            )
            if resp.status_code != 200:
                return {}
            data = resp.json().get("response", [])
    except Exception:
        return {}

    result: dict[int, int] = {}
    for entry in data:
        pid = entry.get("player", {}).get("id")
        if not pid:
            continue
        stats = entry.get("statistics", [{}])[0]
        goals = stats.get("goals", {}).get("total") or 0
        assists = stats.get("goals", {}).get("assists") or 0
        result[pid] = int(goals) + int(assists)

    _topscorer_cache[league_id] = (result, datetime.utcnow())
    return result


async def _build_global_scorer_map() -> dict[int, int]:
    """Fetch all leagues and merge into one player_id -> best_g_a dict."""
    results = await asyncio.gather(*[_fetch_top_scorers(lid) for lid in _CLUB_LEAGUES])
    merged: dict[int, int] = {}
    for r in results:
        for pid, ga in r.items():
            merged[pid] = max(merged.get(pid, 0), ga)
    return merged


async def _get_team_form_mult(team_code: str, scorer_map: dict[int, int]) -> float:
    """
    Return lambda multiplier for a team based on how many squad members
    appear in the top-scorer lists with >= _IN_FORM_THRESHOLD G+A.
    """
    cached = _team_form_cache.get(team_code)
    if cached and (datetime.utcnow() - cached[1]) < _FORM_TTL:
        return cached[0]

    squad_ids = await get_squad_player_ids(team_code)
    if not squad_ids:
        return 1.0

    in_form = sum(
        1 for pid in squad_ids
        if scorer_map.get(pid, 0) >= _IN_FORM_THRESHOLD
    )

    # Ratio relative to expected average; clamp to ±2x deviation
    ratio = (in_form - _EXPECTED_COUNT) / max(_EXPECTED_COUNT, 1)
    ratio = max(-1.0, min(1.0, ratio))
    mult = round(1.0 + _XG_SCALE * ratio, 4)

    _team_form_cache[team_code] = (mult, datetime.utcnow())
    return mult


async def get_squad_attack_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """
    Return (home_mult, away_mult) based on club-season form of squad members.
    Returns (1.0, 1.0) when API key not set or data unavailable.
    """
    if not _API_KEY:
        return 1.0, 1.0

    scorer_map = await _build_global_scorer_map()
    if not scorer_map:
        return 1.0, 1.0

    home_mult, away_mult = await asyncio.gather(
        _get_team_form_mult(home_code, scorer_map),
        _get_team_form_mult(away_code, scorer_map),
    )
    return home_mult, away_mult
