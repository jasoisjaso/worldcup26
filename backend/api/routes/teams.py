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


_POS_ORDER = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Attacker": 3}


@router.get("/{code}/squad-rich")
def squad_rich(code: str, db: Session = Depends(get_db)):
    """Rich squad: PlayerProfile joined with PlayerTournamentStats. Photo URLs,
    season goals/assists/minutes, sorted by position then by goal contribution.

    Backs the photo-grid on /team/{code}. Zero API quota cost — pure DB read."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import PlayerProfile, PlayerTournamentStats, PlayerHistory
    from sqlalchemy import func
    team_api_id = TEAM_IDS.get(code.lower())
    if not team_api_id:
        return {"players": [], "total": 0}
    players = (
        db.query(PlayerProfile)
        .filter(PlayerProfile.team_id == team_api_id)
        .all()
    )
    stats_by_pid = {
        s.player_id: s
        for s in db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.team_id == team_api_id)
        .all()
    }
    # Fallback to harvested per-match PlayerHistory (career/recent games from
    # /players + /fixtures/players) so a squad shows REAL numbers even before the
    # WC tournament-stats aggregator has anything — most of a player's stats are
    # their club/international history, not the 2-3 WC games. Aggregate goals/
    # assists/minutes + appearance count per player from every archived fixture.
    pids = [p.player_id for p in players if p.player_id is not None]
    history_agg: dict[int, dict] = {}
    if pids:
        rows = (
            db.query(
                PlayerHistory.api_player_id,
                func.sum(PlayerHistory.goals),
                func.sum(PlayerHistory.assists),
                func.sum(PlayerHistory.minutes),
                func.count(PlayerHistory.id),
                func.avg(PlayerHistory.rating),
            )
            .filter(PlayerHistory.api_player_id.in_(pids))
            .group_by(PlayerHistory.api_player_id)
            .all()
        )
        for pid, g, a, mins, apps, rating in rows:
            history_agg[pid] = {
                "goals": int(g or 0),
                "assists": int(a or 0),
                "minutes": int(mins or 0),
                "appearances": int(apps or 0),
                "avg_rating": round(float(rating), 2) if rating else None,
            }

    def to_dict(p):
        s = stats_by_pid.get(p.player_id)
        h = history_agg.get(p.player_id)
        # Prefer the WC tournament aggregate; fall back to harvested career
        # history so the squad isn't blank while the WC aggregator is empty.
        stats = None
        if s and (s.appearances or s.goals or s.minutes):
            stats = {
                "appearances": s.appearances or 0,
                "goals": s.goals or 0,
                "assists": s.assists or 0,
                "minutes": s.minutes or 0,
                "yellow_cards": s.yellow_cards or 0,
                "red_cards": s.red_cards or 0,
                "source": "wc",
            }
        elif h and (h["appearances"] or h["goals"] or h["minutes"]):
            stats = {
                "appearances": h["appearances"],
                "goals": h["goals"],
                "assists": h["assists"],
                "minutes": h["minutes"],
                "yellow_cards": 0,
                "red_cards": 0,
                "avg_rating": h["avg_rating"],
                "source": "career",
            }
        return {
            "player_id": p.player_id,
            "name": p.name,
            "position": p.position or "Unknown",
            "age": p.age,
            "nationality": p.nationality,
            "height": p.height,
            "weight": p.weight,
            "photo_url": p.photo_url,
            "stats": stats,
        }
    rows = sorted(
        [to_dict(p) for p in players],
        key=lambda x: (
            _POS_ORDER.get(x["position"], 99),
            -((x["stats"]["goals"] if x["stats"] else 0)),
            -((x["stats"]["assists"] if x["stats"] else 0)),
            x["name"] or "",
        ),
    )
    return {"players": rows, "total": len(rows)}


@router.get("/{code}/recent-form")
def recent_form(code: str, n: int = 5, db: Session = Depends(get_db)):
    """Last N completed matches for this team. Returns oldest→newest so the
    UI strip reads left-to-right like a normal form line.

    Zero API cost — straight DB read against our existing Match table."""
    rows = (
        db.query(Match)
        .filter(or_(Match.home_code == code, Match.away_code == code))
        .filter(Match.status == "complete")
        .order_by(Match.kickoff.desc())
        .limit(n)
        .all()
    )

    def result(m):
        if m.home_score is None or m.away_score is None:
            return None
        is_home = m.home_code == code
        mine = m.home_score if is_home else m.away_score
        theirs = m.away_score if is_home else m.home_score
        if mine > theirs: return "W"
        if mine < theirs: return "L"
        return "D"

    # Pre-fetch opponent names in one query so the rows can show "Brazil 2-1"
    # instead of "br 2-1" — the FormStrip row layout (2026-06-21) needs the
    # readable name, not the ISO code.
    opp_codes = {(m.away_code if m.home_code == code else m.home_code) for m in rows}
    opp_names = {
        t.code: t.name
        for t in db.query(Team).filter(Team.code.in_(opp_codes)).all()
    } if opp_codes else {}

    return {
        "form": [
            {
                "match_id": m.id,
                "opponent_code": (opp := (m.away_code if m.home_code == code else m.home_code)),
                "opponent_name": opp_names.get(opp, opp.upper()),
                "score": f"{m.home_score}-{m.away_score}",
                "result": result(m),
                "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                "venue": "H" if m.home_code == code else "A",
            }
            for m in reversed(rows)
        ]
    }
