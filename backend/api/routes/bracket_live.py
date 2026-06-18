"""
Live knockout bracket: seeds the actual WC2026 R32 bracket from completed group
standings. Once a group is finished, its teams take their real slots. Groups that
haven't finished yet show projected teams from the tournament sim.

GET /tournament/bracket-live
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.models.tournament_sim import load_bracket, match_thirds

router = APIRouter()


def _read_standings(db: Session):
    """Return {group: [(code, pts, gd, gf, played), ...]} ordered by rank."""
    matches = db.query(Match).filter(Match.status == "complete").all()
    teams = {t.code: t.name for t in db.query(Team).all()}

    # Build per-group results
    groups: dict[str, dict[str, dict]] = {}
    for m in matches:
        g = m.group
        if g not in groups:
            groups[g] = {}
        for code in (m.home_code, m.away_code):
            if code not in groups[g]:
                groups[g][code] = {"pts": 0, "gd": 0, "gf": 0, "ga": 0, "played": 0}

        h, a = groups[g][m.home_code], groups[g][m.away_code]
        h["played"] += 1
        a["played"] += 1
        h["gf"] += (m.home_score or 0)
        h["ga"] += (m.away_score or 0)
        a["gf"] += (m.away_score or 0)
        a["ga"] += (m.home_score or 0)
        if m.home_score > m.away_score:
            h["pts"] += 3
        elif m.away_score > m.home_score:
            a["pts"] += 3
        else:
            h["pts"] += 1
            a["pts"] += 1

    for g in groups:
        for c in groups[g]:
            groups[g][c]["gd"] = groups[g][c]["gf"] - groups[g][c]["ga"]

    # Rank each group
    standings: dict[str, list[dict]] = {}
    for g, codes in groups.items():
        ranked = sorted(
            codes.items(),
            key=lambda kv: (kv[1]["pts"], kv[1]["gd"], kv[1]["gf"]),
            reverse=True,
        )
        standings[g] = [{"code": c, "name": teams.get(c, c), **stats} for c, stats in ranked]

    return standings, teams


def _group_done(group: str, standings: dict[str, list[dict]]) -> bool:
    """A group is done when all 4 teams have played 3 matches."""
    if group not in standings:
        return False
    return all(t["played"] == 3 for t in standings[group])


def _best_thirds(standings: dict[str, list[dict]]) -> list[str]:
    """Return the 8 qualifying third-place groups sorted by points/GD/GF."""
    pool = []
    for g, ranked in standings.items():
        if len(ranked) >= 3 and ranked[2]["played"] == 3:
            t = ranked[2]
            pool.append((t["pts"], t["gd"], t["gf"], g))
    pool.sort(reverse=True)
    return [g for _, _, _, g in pool[:8]]


@router.get("/bracket-live")
def bracket_live(db: Session = Depends(get_db)):
    """The actual seeded knockout bracket, using completed group standings."""
    bracket = load_bracket()
    standings, teams = _read_standings(db)
    r32 = bracket["r32"]
    third_table = bracket["third_table"]

    # Determine which groups are done
    done_groups = {g for g in standings if _group_done(g, standings)}

    # Which third-place groups qualify
    qualifying_thirds = set(_best_thirds(standings))

    def _resolve(slot: str, match_no: int) -> dict | None:
        """Resolve a slot like '1A', '2B', or third-place."""
        kind = slot[0]
        grp = slot[1:]
        if grp not in done_groups:
            return None  # Group not done
        ranked = standings[grp]
        if kind == "1":
            return ranked[0]
        if kind == "2":
            return ranked[1]
        # Third place — need to check if this group qualifies
        if grp in qualifying_thirds:
            # Find which match slot this third gets
            key = "".join(sorted(qualifying_thirds))
            if key in third_table:
                assignment = third_table[key]
                slot_name = f"M{match_no}"
                assigned_grp = assignment.get(slot_name)
                if assigned_grp == grp and len(ranked) >= 3:
                    return ranked[2]
        return None

    rounds = []
    # Round of 32: matches 73-88
    r32_matches = []
    for m in r32:
        h = _resolve(m["home"], m["match"])
        a = _resolve(m["away"], m["match"])
        r32_matches.append({
            "match": m["match"],
            "home_rule": m["home"],
            "away_rule": m["away"],
            "home": h,
            "away": a,
            "locked": h is not None and a is not None,
        })
    rounds.append({"name": "Round of 32", "matches": r32_matches})

    # Later rounds: show TBD
    for rname in ["Round of 16", "Quarter-finals", "Semi-finals", "Final"]:
        rounds.append({"name": rname, "matches": [], "tbd": True})

    # Summary
    groups_summary = {}
    for g in sorted(standings.keys()):
        done = _group_done(g, standings)
        ranked = standings[g]
        groups_summary[g] = {
            "done": done,
            "teams": [
                {
                    "code": t["code"],
                    "name": t["name"],
                    "pos": i + 1,
                    "pts": t["pts"],
                    "gd": t["gd"],
                    "played": t["played"],
                }
                for i, t in enumerate(ranked)
            ],
        }

    return {
        "groups_done": len(done_groups),
        "total_groups": 12,
        "third_qualifiers": sorted(qualifying_thirds) if qualifying_thirds else [],
        "groups": groups_summary,
        "bracket": {"rounds": rounds},
    }
