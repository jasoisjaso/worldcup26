from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_

from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.data.fetchers.injuries import get_squad_details
from backend.data.fetchers.set_pieces import _SET_PIECE_DATA
from backend.models.elo_model import elo_to_lambdas

router = APIRouter()

# Radar axes — each team scored 0-100 as a percentile vs the 48-team field, so the polygon
# reads as "where this team sits in the tournament", StatsBomb-style.
RADAR_AXES = ["Attack", "Defence", "Rating", "Set-piece att", "Set-piece def"]


def _radar_raw(db: Session) -> dict[str, dict[str, float]]:
    raw: dict[str, dict[str, float]] = {}
    for t in db.query(Team).all():
        lh, la = elo_to_lambdas(t.elo or 1500.0, 1500.0, t.code, "")
        sp = _SET_PIECE_DATA.get(t.code, (0.0, 0.0))
        raw[t.code] = {
            "Attack": lh,            # expected goals vs an average side
            "Defence": -la,          # fewer conceded = stronger (negated so higher = better)
            "Rating": t.elo or 1500.0,
            "Set-piece att": sp[0],
            "Set-piece def": sp[1],
        }
    return raw


def _percentiles(raw: dict[str, dict[str, float]]) -> dict[str, dict[str, int]]:
    codes = list(raw)
    n = max(1, len(codes) - 1)
    out: dict[str, dict[str, int]] = {c: {} for c in codes}
    for axis in RADAR_AXES:
        vals = [raw[c][axis] for c in codes]
        for c in codes:
            v = raw[c][axis]
            rank = sum(1 for x in vals if x < v)
            out[c][axis] = round(rank / n * 100)
    return out


@router.get("/radar")
def get_radar(db: Session = Depends(get_db)):
    """Percentile radar metrics for every team (0-100 vs the field)."""
    pcts = _percentiles(_radar_raw(db))
    teams = {}
    for code, values in pcts.items():
        t = db.get(Team, code)
        if not t:
            continue
        teams[code] = {
            "code": code, "name": t.name, "flag_url": t.flag_url,
            "primary_color": t.primary_color, "values": values,
        }
    return {"axes": RADAR_AXES, "teams": teams}

_MANAGERS: dict[str, str] = {
    # UEFA
    "fr": "Didier Deschamps",
    "es": "Luis de la Fuente",
    "pt": "Roberto Martinez",
    "de": "Julian Nagelsmann",
    "nl": "Ronald Koeman",
    "be": "Domenico Tedesco",
    "gb-eng": "Thomas Tuchel",
    "hr": "Zlatko Dalic",
    "ch": "Murat Yakin",
    "tr": "Vincenzo Montella",
    "at": "Ralf Rangnick",
    "no": "Stale Solbakken",
    "cz": "Ivan Hasek",
    "gb-sct": "Steve Clarke",
    "ba": "Sergej Barbarez",
    "se": "Jon Dahl Tomasson",
    # CONMEBOL
    "ar": "Lionel Scaloni",
    "br": "Dorival Jr.",
    "co": "Nestor Lorenzo",
    "uy": "Marcelo Bielsa",
    "ec": "Sebastian Beccacece",
    "py": "Gustavo Alfaro",
    # AFC
    "jp": "Hajime Moriyasu",
    "ir": "Amir Ghalenoei",
    "kr": "Hong Myung-bo",
    "au": "Tony Popovic",
    "sa": "Roberto Mancini",
    "uz": "Srecko Katanec",
    "qa": "Marquez Lopez",
    "jo": "Adnan Hamad",
    "iq": "Jesus Casas",
    # CONCACAF
    "mx": "Javier Aguirre",
    "us": "Mauricio Pochettino",
    "ca": "Jesse Marsch",
    "pa": "Thomas Christiansen",
    "cw": "Remko Bicentini",
    "ht": "Marc Collat",
    # CAF
    "ma": "Walid Regragui",
    "sn": "Aliou Cisse",
    "ci": "Emerse Fae",
    "eg": "Hossam Hassan",
    "dz": "Vladimir Petkovic",
    "tn": "Jalel Kadri",
    "cd": "Sebastien Desabre",
    "za": "Hugo Broos",
    "gh": "Otto Addo",
    "cv": "Pedro Leitao Brito",
    # OFC
    "nz": "Darren Bazeley",
}


@router.get("/{code}/profile")
async def get_team_profile(code: str, db: Session = Depends(get_db)):
    team = db.get(Team, code)
    if not team:
        return {"error": "Team not found"}

    squad = await get_squad_details(code)

    sp = _SET_PIECE_DATA.get(code, (0.0, 0.0))
    manager = _MANAGERS.get(code, "")

    upcoming = (
        db.query(Match)
        .filter(
            or_(Match.home_code == code, Match.away_code == code),
            Match.status == "upcoming",
        )
        .order_by(Match.kickoff)
        .limit(3)
        .all()
    )

    fixtures = []
    for m in upcoming:
        opp_code = m.away_code if m.home_code == code else m.home_code
        opp_team = db.get(Team, opp_code)
        fixtures.append({
            "match_id": m.id,
            "opponent_code": opp_code,
            "opponent": opp_team.name if opp_team else opp_code.upper(),
            "opponent_flag": opp_team.flag_url if opp_team else "",
            "is_home": m.home_code == code,
            "kickoff": m.kickoff.isoformat() if m.kickoff else None,
            "group": m.group,
            "matchday": m.matchday,
        })

    return {
        "code": code,
        "name": team.name,
        "flag_url": team.flag_url,
        "primary_color": team.primary_color,
        "elo": team.elo,
        "fifa_ranking": team.fifa_ranking,
        "manager": manager,
        "set_piece_attack": sp[0],
        "set_piece_defense": sp[1],
        "squad": squad,
        "upcoming_fixtures": fixtures,
    }
