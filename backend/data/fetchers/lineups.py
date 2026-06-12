"""
Confirmed lineup fetcher for WC2026 predictions.

Detects key player absences from the confirmed starting XI and bench
(~60-90 min pre-kickoff) and returns lambda multipliers per team.

Returns (1.0, 1.0) until the lineup is officially confirmed. Supersedes
the injury signal once ground-truth lineup data is available.

Uses API_FOOTBALL_KEY from environment (same key as injuries.py).
Player IDs are validated against the squad list to prevent false positives
from stale or wrong IDs — if an ID isn't in the squad, it's ignored.
"""
from __future__ import annotations
import asyncio
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.data.fetchers.injuries import TEAM_IDS, get_upcoming_fixture_id, get_squad_player_ids

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

_fixture_id_cache: dict[str, tuple[Optional[int], datetime]] = {}
_lineup_cache: dict[int, tuple[dict, datetime]] = {}
_reason_store: dict[str, str] = {}   # team_code -> human-readable reason string

_FIXTURE_TTL = timedelta(hours=12)
_LINEUP_TTL = timedelta(minutes=30)

# (api_football_player_id, absent_mult, name)
# absent_mult: lambda factor when player is NOT in startXI or bench (confirmed absent)
# bench penalty is half of absent penalty (might come on as sub)
# IDs marked # verify should be cross-checked via /players/squads?team=X
KEY_PLAYERS: dict[str, list[tuple[int, float, str]]] = {
    "ar":     [(154,    0.84, "Messi"),          (165240, 0.93, "Lautaro Martinez")],
    "br":     [(47232,  0.87, "Vinicius Jr"),     (184029, 0.94, "Rodrygo")],
    "fr":     [(278,    0.87, "Mbappe"),          (97,     0.95, "Griezmann")],
    "gb-eng": [(1485,   0.91, "Bellingham"),      (253682, 0.94, "Saka")],
    "es":     [(722757, 0.93, "Pedri"),           (284413, 0.92, "Yamal")],
    "pt":     [(874,    0.86, "Ronaldo"),         (667,    0.93, "Bruno Fernandes")],
    "de":     [(389773, 0.92, "Musiala"),         (389776, 0.93, "Wirtz")],        # verify Wirtz
    "nl":     [(233614, 0.93, "Gakpo"),           (2295,   0.95, "Van Dijk")],
    "be":     [(1254,   0.87, "De Bruyne"),       (2460,   0.93, "Lukaku")],
    "hr":     [(521,    0.90, "Modric")],
    "uy":     [(200034, 0.91, "Darwin Nunez")],
    "co":     [(195353, 0.92, "Luis Diaz"),       (2298,   0.93, "James Rodriguez")],
    "ma":     [(184240, 0.93, "Hakimi"),          (236884, 0.94, "En-Nesyri")],
    "jp":     [(165519, 0.93, "Mitoma"),          (219716, 0.94, "Kubo")],         # verify both
    "kr":     [(2281,   0.89, "Son Heung-min")],
    "us":     [(15725,  0.91, "Pulisic")],
    "sn":     [(73,     0.90, "Mane")],                                             # verify ID
    "ch":     [(3297,   0.93, "Xhaka")],                                            # verify ID
    "mx":     [(2476,   0.94, "Guardado")],                                         # verify ID
    "eg":     [(9763,   0.90, "Salah")],                                            # verify ID
}


async def _get_fixture_id(home_code: str, away_code: str) -> Optional[int]:
    key = f"{home_code}-{away_code}"
    cached = _fixture_id_cache.get(key)
    if cached and (datetime.utcnow() - cached[1]) < _FIXTURE_TTL:
        return cached[0]

    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id or not away_id:
        _fixture_id_cache[key] = (None, datetime.utcnow())
        return None

    fid = await get_upcoming_fixture_id(home_id, away_id)
    _fixture_id_cache[key] = (fid, datetime.utcnow())
    return fid


async def _fetch_lineups(fixture_id: int) -> dict:
    """
    Returns {"home_team_id": int, "away_team_id": int,
             "home_start": set[int], "home_bench": set[int],
             "away_start": set[int], "away_bench": set[int]}
    or {} if lineup not yet confirmed.
    """
    cached = _lineup_cache.get(fixture_id)
    if cached and (datetime.utcnow() - cached[1]) < _LINEUP_TTL:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_BASE}/fixtures/lineups",
                headers=_HEADERS,
                params={"fixture": fixture_id},
            )
            if resp.status_code != 200:
                return {}
            teams = resp.json().get("response", [])
    except Exception:
        return {}

    if len(teams) < 2:
        return {}

    def _extract(team_data: dict) -> tuple[int, set[int], set[int]]:
        tid = team_data.get("team", {}).get("id", 0)
        start = {
            p["player"]["id"]
            for p in team_data.get("startXI", [])
            if p.get("player", {}).get("id")
        }
        bench = {
            p["player"]["id"]
            for p in team_data.get("substitutes", [])
            if p.get("player", {}).get("id")
        }
        return tid, start, bench

    t1_id, t1_start, t1_bench = _extract(teams[0])
    t2_id, t2_start, t2_bench = _extract(teams[1])

    if len(t1_start) < 11 or len(t2_start) < 11:
        # Lineup not confirmed yet
        _lineup_cache[fixture_id] = ({}, datetime.utcnow())
        return {}

    result = {
        "team1_id": t1_id, "team2_id": t2_id,
        "team1_start": t1_start, "team1_bench": t1_bench,
        "team2_start": t2_start, "team2_bench": t2_bench,
    }
    _lineup_cache[fixture_id] = (result, datetime.utcnow())
    return result


def _calc_mult(
    team_code: str,
    squad_ids: set[int],
    start_ids: set[int],
    bench_ids: set[int],
) -> tuple[float, str]:
    """
    Return (multiplier, reason_string) for a team based on key player lineup status.
    Absent from both start+bench = full penalty.
    On bench only (not starting) = half penalty.
    """
    key_players = KEY_PLAYERS.get(team_code, [])
    mult = 1.0
    absent_names = []
    benched_names = []

    for player_id, absent_mult, name in key_players:
        if player_id not in squad_ids:
            continue  # ID not in squad — wrong ID or player not called up, skip
        if player_id in start_ids:
            continue  # Starting — no penalty
        if player_id in bench_ids:
            # Benched: half penalty
            bench_mult = 1.0 - (1.0 - absent_mult) * 0.5
            mult *= bench_mult
            benched_names.append(name)
        else:
            # Absent from lineup entirely
            mult *= absent_mult
            absent_names.append(name)

    mult = max(0.75, mult)

    parts = []
    if absent_names:
        parts.append(f"absent: {', '.join(absent_names)}")
    if benched_names:
        parts.append(f"benched: {', '.join(benched_names)}")
    reason = "; ".join(parts)
    return round(mult, 4), reason


async def get_lineup_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """
    Return (home_mult, away_mult) based on confirmed lineup.
    Returns (1.0, 1.0) when lineup not yet confirmed or API key not set.
    """
    if not _API_KEY:
        return 1.0, 1.0

    fixture_id = await _get_fixture_id(home_code, away_code)
    if not fixture_id:
        return 1.0, 1.0

    lineup_data = await _fetch_lineups(fixture_id)
    if not lineup_data:
        return 1.0, 1.0

    home_api_id = TEAM_IDS.get(home_code, 0)
    away_api_id = TEAM_IDS.get(away_code, 0)

    # Map team IDs to home/away
    if lineup_data["team1_id"] == home_api_id:
        home_start = lineup_data["team1_start"]
        home_bench = lineup_data["team1_bench"]
        away_start = lineup_data["team2_start"]
        away_bench = lineup_data["team2_bench"]
    else:
        home_start = lineup_data["team2_start"]
        home_bench = lineup_data["team2_bench"]
        away_start = lineup_data["team1_start"]
        away_bench = lineup_data["team1_bench"]

    home_squad, away_squad = await asyncio.gather(
        get_squad_player_ids(home_code),
        get_squad_player_ids(away_code),
    )

    home_mult, home_reason = _calc_mult(home_code, home_squad, home_start, home_bench)
    away_mult, away_reason = _calc_mult(away_code, away_squad, away_start, away_bench)

    _reason_store[home_code] = home_reason
    _reason_store[away_code] = away_reason

    return home_mult, away_mult


def get_lineup_reason(team_code: str) -> str:
    return _reason_store.get(team_code, "")
