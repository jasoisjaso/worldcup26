"""Global search — teams + players. Zero-API-cost, hits local DB only.

Powers the search bar in the TopBar. Returns up to 6 teams and 6 players that
match a substring of the name, ordered by best-match heuristic:
  1. exact prefix match (case-insensitive)
  2. word-boundary match
  3. plain substring

Teams resolve to /team/{code}, players to /player/{player_id}. Both surfaces
already exist, so the search bar is pure routing glue.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Team, PlayerProfile
from backend.data.fetchers.injuries import TEAM_IDS

router = APIRouter()


_WC_TEAM_API_IDS = set(TEAM_IDS.values())


def _team_code_for_api_id(team_api_id: int | None) -> str | None:
    if not team_api_id:
        return None
    for code, api_id in TEAM_IDS.items():
        if api_id == team_api_id:
            return code
    return None


def _rank_match(name: str, q_lower: str) -> int:
    """Lower is better. Prefix < word-boundary < substring."""
    n = (name or "").lower()
    if n.startswith(q_lower):
        return 0
    if f" {q_lower}" in n:
        return 1
    return 2


@router.get("")
def search(
    q: str = Query("", min_length=0, max_length=40),
    db: Session = Depends(get_db),
):
    """Search teams + players by substring. Empty query returns empty lists
    (the client should not call us without input)."""
    q_clean = (q or "").strip()
    if len(q_clean) < 2:
        return {"teams": [], "players": [], "query": q_clean}

    q_lower = q_clean.lower()
    like = f"%{q_lower}%"

    # Teams: cheap, 48 rows max.
    team_rows = (
        db.query(Team)
        .filter(func.lower(Team.name).like(like))
        .all()
    )
    team_rows.sort(key=lambda t: (_rank_match(t.name, q_lower), t.name or ""))
    teams = [
        {
            "code": t.code,
            "name": t.name,
            "flag_url": t.flag_url,
            "elo": int(t.elo or 0),
        }
        for t in team_rows[:6]
    ]

    # Players: PlayerProfile may have many rows; limit at SQL level then re-rank.
    player_rows = (
        db.query(PlayerProfile)
        .filter(func.lower(PlayerProfile.name).like(like))
        .limit(40)
        .all()
    )
    player_rows.sort(key=lambda p: (_rank_match(p.name, q_lower), p.name or ""))
    players = []
    for p in player_rows[:6]:
        nation_code = _team_code_for_api_id(p.team_id)
        players.append({
            "id": p.player_id,
            "name": p.name,
            "position": p.position,
            "team_name": p.team_name,
            "photo_url": p.photo_url,
            "nation_code": nation_code,
            "is_wc_team": p.team_id in _WC_TEAM_API_IDS if p.team_id else False,
        })

    return {"teams": teams, "players": players, "query": q_clean}
