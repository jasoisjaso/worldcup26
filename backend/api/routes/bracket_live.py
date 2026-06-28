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
from backend.models.tournament_sim import load_bracket

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


def _resolve_from_rules(
    standings: dict[str, list[dict]],
    done_groups: set[str],
    qualifying_thirds: set[str],
    third_table: dict,
    slot: str,
    match_no: int,
) -> dict | None:
    """Resolve a slot like '1A', '2B', or '3(ABCDF)' from current group standings.
    Returns None when the slot can't be locked yet. Used as the fallback path
    when no R32 Match rows have been seeded; once seed_knockout has run,
    bracket_live prefers reading the Match table directly.
    """
    kind = slot[0]
    if kind in ("1", "2"):
        grp = slot[1:]
        if grp not in done_groups:
            return None
        rank = 0 if kind == "1" else 1
        return standings[grp][rank]
    if kind != "3":
        return None
    # Third-place compound rule like '3(ABCDF)' or single-group '3F'.
    pool = slot[2:-1] if slot.startswith("3(") else slot[1:]
    candidates = set(pool) & qualifying_thirds
    if not candidates:
        return None
    key = "".join(sorted(qualifying_thirds))
    assignment = third_table.get(key, {})
    assigned_grp = assignment.get(f"M{match_no}")
    if assigned_grp in candidates and assigned_grp in standings and len(standings[assigned_grp]) >= 3:
        return standings[assigned_grp][2]
    return None


def _team_view(db: Session, code: str | None) -> dict | None:
    if not code:
        return None
    t = db.get(Team, code)
    if not t:
        return None
    return {"code": t.code, "name": t.name, "flag_url": t.flag_url, "primary_color": t.primary_color}


@router.get("/bracket-live")
def bracket_live(db: Session = Depends(get_db)):
    """The actual seeded knockout bracket. Prefers MD4+ Match rows when
    seed_knockout has been run (post-group-stage); falls back to synthesising
    from standings + Annex C when the rows aren't in yet."""
    bracket = load_bracket()
    standings, teams = _read_standings(db)
    r32_spec = bracket["r32"]
    third_table = bracket["third_table"]

    done_groups = {g for g in standings if _group_done(g, standings)}
    qualifying_thirds = set(_best_thirds(standings))

    # Preferred path: MD4 Match rows already seeded with concrete teams.
    seeded = {m.id: m for m in db.query(Match).filter(Match.matchday == 4).all()}

    rounds = []
    r32_matches = []
    for spec in r32_spec:
        mid = f"M{spec['match']:03d}"
        seeded_row = seeded.get(mid)
        if seeded_row:
            h = _team_view(db, seeded_row.home_code)
            a = _team_view(db, seeded_row.away_code)
        else:
            h = _resolve_from_rules(standings, done_groups, qualifying_thirds, third_table, spec["home"], spec["match"])
            a = _resolve_from_rules(standings, done_groups, qualifying_thirds, third_table, spec["away"], spec["match"])
        r32_matches.append({
            "match": spec["match"],
            "home_rule": spec["home"],
            "away_rule": spec["away"],
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
