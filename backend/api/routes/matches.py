from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team

router = APIRouter()


def _team_dict(team: Team) -> dict:
    return {
        "code": team.code,
        "name": team.name,
        "fifa_code": team.fifa_code,
        "elo": team.elo,
        "fifa_ranking": team.fifa_ranking,
        "flag_url": team.flag_url,
        "primary_color": team.primary_color,
    }


def _match_dict(match: Match, home: Team, away: Team) -> dict:
    return {
        "id": match.id,
        "group": match.group,
        "matchday": match.matchday,
        "kickoff": match.kickoff.isoformat() if match.kickoff else None,
        "venue": match.venue,
        "status": match.status,
        "home": _team_dict(home),
        "away": _team_dict(away),
        "actual_score": (
            {"home": match.home_score, "away": match.away_score}
            if match.home_score is not None
            else None
        ),
    }


@router.get("")
def get_matches(group: str | None = None, matchday: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Match)
    if group:
        query = query.filter(Match.group == group.upper())
    if matchday:
        query = query.filter(Match.matchday == matchday)
    matches = query.order_by(Match.kickoff).all()

    result = []
    for m in matches:
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if home and away:
            result.append(_match_dict(m, home, away))
    return result


@router.get("/{match_id}")
def get_match(match_id: str, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)
    return _match_dict(m, home, away)
