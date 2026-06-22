"""Per-player profile endpoint, zero-API-cost.

Reads PlayerProfile + PlayerTournamentStats + PlayerHistory only — no external
calls. Powers the /player/[id] page that users land on after clicking a player
card on a team page.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import PlayerProfile, PlayerTournamentStats, PlayerHistory, Team
from backend.data.fetchers.injuries import TEAM_IDS

router = APIRouter()


def _team_code_for_api_id(team_api_id: int | None) -> str | None:
    """Reverse-lookup our internal 2-letter code from the api-football team id.
    Only resolves for WC teams (the TEAM_IDS map). Returns None for club teams
    (Liverpool, Real Madrid etc.) which don't have an internal Team row."""
    if not team_api_id:
        return None
    for code, api_id in TEAM_IDS.items():
        if api_id == team_api_id:
            return code
    return None


@router.get("/{player_id}/profile")
def player_profile(player_id: int, db: Session = Depends(get_db)):
    """Everything we know about a player: photo, vitals, career stats, recent
    appearances. Career stats are summed across PlayerTournamentStats rows
    (player may have multiple, one per club we've tracked them through)."""
    p = db.query(PlayerProfile).filter(PlayerProfile.player_id == player_id).first()
    if not p:
        raise HTTPException(404, "player not found")

    career = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == player_id)
        .all()
    )
    recent = (
        db.query(PlayerHistory)
        .filter(PlayerHistory.api_player_id == player_id)
        .order_by(PlayerHistory.id.desc())
        .limit(10)
        .all()
    )

    # Career totals (sum across all teams tracked)
    totals = {
        "appearances": sum(s.appearances or 0 for s in career),
        "goals": sum(s.goals or 0 for s in career),
        "assists": sum(s.assists or 0 for s in career),
        "minutes": sum(s.minutes or 0 for s in career),
        "yellow_cards": sum(s.yellow_cards or 0 for s in career),
        "red_cards": sum(s.red_cards or 0 for s in career),
        # Spot-kick summary. attempts > 0 is the gate the UI uses to decide
        # whether to render the conversion-rate strip — players who have
        # never stepped up shouldn't have a 0/0 panel taking up space.
        "penalty_attempts": sum(getattr(s, "penalty_attempts", 0) or 0 for s in career),
        "penalty_goals": sum(s.penalty_goals or 0 for s in career),
        "penalty_misses": sum(getattr(s, "penalty_misses", 0) or 0 for s in career),
        "shootout_penalty_goals": sum(getattr(s, "shootout_penalty_goals", 0) or 0 for s in career),
        "shootout_penalty_misses": sum(getattr(s, "shootout_penalty_misses", 0) or 0 for s in career),
    }

    # National-team code if this player's team is a WC team
    nation_code = _team_code_for_api_id(p.team_id)
    nation_team = db.get(Team, nation_code) if nation_code else None

    return {
        "player": {
            "id": p.player_id,
            "name": p.name,
            "firstname": p.firstname,
            "lastname": p.lastname,
            "age": p.age,
            "position": p.position,
            "nationality": p.nationality,
            "height": p.height,
            "weight": p.weight,
            "photo_url": p.photo_url,
            "team_id": p.team_id,
            "team_name": p.team_name,
            # If their team is a WC team, expose the code so the page can link back.
            "nation_code": nation_code,
            "nation_name": nation_team.name if nation_team else None,
            "nation_flag": nation_team.flag_url if nation_team else None,
        },
        "totals": totals,
        "career_stats": [
            {
                "team_id": s.team_id,
                "team_name": s.team_name,
                "tournament": s.tournament,
                "appearances": s.appearances or 0,
                "goals": s.goals or 0,
                "assists": s.assists or 0,
                "minutes": s.minutes or 0,
                "yellow_cards": s.yellow_cards or 0,
                "red_cards": s.red_cards or 0,
            }
            for s in career
        ],
        "recent_matches": [
            {
                "api_fixture_id": h.api_fixture_id,
                "match_id": h.match_id,
                "goals": h.goals or 0,
                "assists": h.assists or 0,
                "minutes": h.minutes or 0,
                "rating": h.rating,
                "captured_at": h.captured_at.isoformat() if h.captured_at else None,
            }
            for h in recent
        ],
    }
