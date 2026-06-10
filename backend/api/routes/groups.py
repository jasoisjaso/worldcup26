from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team

router = APIRouter()


def _standing(team: Team, played: int, w: int, d: int, l: int, gf: int, ga: int) -> dict:
    pts = w * 3 + d
    return {
        "code": team.code,
        "name": team.name,
        "flag_url": team.flag_url,
        "primary_color": team.primary_color,
        "played": played,
        "won": w,
        "drawn": d,
        "lost": l,
        "gf": gf,
        "ga": ga,
        "gd": gf - ga,
        "points": pts,
    }


@router.get("")
def get_groups(db: Session = Depends(get_db)):
    matches = db.query(Match).order_by(Match.group, Match.matchday).all()

    # accumulate stats per group per team
    groups: dict[str, dict[str, dict]] = {}
    for m in matches:
        g = m.group
        if not g:
            continue
        if g not in groups:
            groups[g] = {}
        for code in (m.home_code, m.away_code):
            if code not in groups[g]:
                groups[g][code] = {"played": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0}

        if m.home_score is not None and m.away_score is not None:
            hs, as_ = m.home_score, m.away_score
            groups[g][m.home_code]["played"] += 1
            groups[g][m.away_code]["played"] += 1
            groups[g][m.home_code]["gf"] += hs
            groups[g][m.home_code]["ga"] += as_
            groups[g][m.away_code]["gf"] += as_
            groups[g][m.away_code]["ga"] += hs
            if hs > as_:
                groups[g][m.home_code]["w"] += 1
                groups[g][m.away_code]["l"] += 1
            elif as_ > hs:
                groups[g][m.away_code]["w"] += 1
                groups[g][m.home_code]["l"] += 1
            else:
                groups[g][m.home_code]["d"] += 1
                groups[g][m.away_code]["d"] += 1

    result = []
    for group_name in sorted(groups.keys()):
        teams_raw = groups[group_name]
        rows = []
        for code, s in teams_raw.items():
            team = db.get(Team, code)
            if team:
                rows.append(_standing(team, s["played"], s["w"], s["d"], s["l"], s["gf"], s["ga"]))
        rows.sort(key=lambda r: (-r["points"], -r["gd"], -r["gf"], r["name"]))
        result.append({"group": group_name, "teams": rows})

    return result
