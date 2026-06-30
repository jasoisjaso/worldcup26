"""
Group progression scenarios for Matchday 3.
For each team with matches remaining, show what they need to advance.

GET /groups/scenarios
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team
from backend.util.datetime import iso_utc

router = APIRouter()


def _read_standings(db: Session):
    matches = db.query(Match).all()
    teams_lookup = {t.code: t.name for t in db.query(Team).all()}

    groups: dict[str, dict[str, dict]] = {}
    for m in matches:
        g = m.group
        if g not in groups:
            groups[g] = {}
        for code in (m.home_code, m.away_code):
            if code not in groups[g]:
                groups[g][code] = {"pts": 0, "gd": 0, "gf": 0, "ga": 0, "played": 0}

        if m.status == "complete" and m.home_score is not None:
            h, a = groups[g][m.home_code], groups[g][m.away_code]
            h["played"] += 1
            a["played"] += 1
            h["gf"] += m.home_score
            h["ga"] += m.away_score
            a["gf"] += m.away_score
            a["ga"] += m.home_score
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

    return groups, teams_lookup


def _remaining_matches(db: Session, group: str) -> list[Match]:
    return (
        db.query(Match)
        .filter(Match.group == group, Match.status == "upcoming")
        .all()
    )


def _simulate_md3(standings: dict[str, dict], remaining: list[Match]) -> dict[str, dict]:
    """Simulate all possible MD3 outcomes (win/loss/draw combinations) and
    return each team's advancement scenarios."""
    import itertools

    codes = sorted(standings.keys())
    results: dict[str, dict] = {}

    # For each team, track what scenarios they advance in
    for c in codes:
        results[c] = {
            "guaranteed_top2": False,
            "guaranteed_advance": False,
            "eliminated": False,
            "need_win": False,
            "need_draw": False,
            "need_help": False,
            "scenarios_advance": 0,
            "total_scenarios": 0,
            "can_win_group": False,
            "max_points": standings[c]["pts"] + 3,
            "min_position": None,
            "max_position": None,
        }

    # Generate all MD3 result combos (3^N where N = remaining matches, max 2 per group)
    outcomes = list(itertools.product([(1, 0), (0, 1), (0, 0)], repeat=len(remaining)))
    positions = {c: [] for c in codes}

    for outcome in outcomes:
        # Simulate this outcome
        sim_standings = {c: dict(standings[c]) for c in codes}
        for i, m in enumerate(remaining):
            hg, ag = outcome[i]
            h, a = m.home_code, m.away_code
            sim_standings[h]["played"] += 1
            sim_standings[a]["played"] += 1
            sim_standings[h]["gf"] += hg
            sim_standings[h]["ga"] += ag
            sim_standings[a]["gf"] += ag
            sim_standings[a]["ga"] += hg
            sim_standings[h]["gd"] = sim_standings[h]["gf"] - sim_standings[h]["ga"]
            sim_standings[a]["gd"] = sim_standings[a]["gf"] - sim_standings[a]["ga"]
            if hg > ag:
                sim_standings[h]["pts"] += 3
            elif ag > hg:
                sim_standings[a]["pts"] += 3
            else:
                sim_standings[h]["pts"] += 1
                sim_standings[a]["pts"] += 1

        # Rank
        ranked = sorted(
            codes,
            key=lambda c: (sim_standings[c]["pts"], sim_standings[c]["gd"], sim_standings[c]["gf"]),
            reverse=True,
        )
        for pos, code in enumerate(ranked):
            positions[code].append(pos + 1)

    # Analyze results
    for c in codes:
        pos_list = positions[c]
        results[c]["total_scenarios"] = len(pos_list)
        results[c]["scenarios_advance"] = sum(1 for p in pos_list if p <= 2)
        results[c]["min_position"] = min(pos_list)
        results[c]["max_position"] = max(pos_list)

        # Guaranteed top 2?
        if results[c]["min_position"] <= 2 and results[c]["max_position"] <= 2:
            results[c]["guaranteed_top2"] = True
            results[c]["guaranteed_advance"] = True

        # Already eliminated?
        if results[c]["min_position"] > 2:
            # Can still advance as best 3rd? Simplified: needs top 2 to be safe
            if results[c]["min_position"] > 2 and results[c]["max_position"] == 3:
                results[c]["need_help"] = True
            elif results[c]["min_position"] >= 4:
                results[c]["eliminated"] = True

        # Need a win?
        advance_if_win = 0
        total_wins = 0
        for oi, outcome in enumerate(outcomes):
            team_wins = any(
                (m.home_code == c and outcome[ri][0] > outcome[ri][1])
                or (m.away_code == c and outcome[ri][1] > outcome[ri][0])
                for ri, m in enumerate(remaining)
            )
            if team_wins:
                total_wins += 1
                if positions[c][oi] <= 2:
                    advance_if_win += 1

        if total_wins > 0 and advance_if_win / total_wins > 0.9:
            results[c]["need_win"] = True

        # Can still win the group?
        results[c]["can_win_group"] = results[c]["min_position"] == 1

    return results


@router.get("/scenarios")
def group_scenarios(
    group: str | None = Query(None, description="Filter to a specific group"),
    db: Session = Depends(get_db),
):
    """For each team still alive in MD3, show what they need to advance."""
    standings, names = _read_standings(db)
    all_groups = sorted(standings.keys())

    output = []
    groups_to_check = [group] if group and group in standings else all_groups

    for g in groups_to_check:
        gs = standings[g]
        remaining = _remaining_matches(db, g)
        if not remaining:
            continue  # Group done

        scenarios = _simulate_md3(gs, remaining)

        teams_out = []
        for code in sorted(gs.keys(), key=lambda c: (gs[c]["pts"], gs[c]["gd"], gs[c]["gf"]), reverse=True):
            sc = scenarios[code]
            # Determine status text
            if sc["guaranteed_top2"]:
                status = "GUARANTEED"
                detail = "Already through to Round of 32"
            elif sc["eliminated"]:
                status = "ELIMINATED"
                detail = "Cannot finish top 2"
            elif sc["need_win"] and sc["can_win_group"]:
                status = "WIN_TO_WIN_GROUP"
                detail = "A win guarantees top spot"
            elif sc["need_win"]:
                status = "NEED_WIN"
                detail = "Must win to have a chance at advancing"
            elif sc["need_help"]:
                status = "NEED_HELP"
                detail = "Need to win AND other results to go their way"
            else:
                status = "IN_CONTENTION"
                detail = "Advancement depends on MD3 results"

            teams_out.append({
                "code": code,
                "name": names.get(code, code),
                "played": gs[code]["played"],
                "pts": gs[code]["pts"],
                "gd": gs[code]["gd"],
                "gf": gs[code]["gf"],
                "max_points": sc["max_points"],
                "min_position": sc["min_position"],
                "max_position": sc["max_position"],
                "scenarios_advance": sc["scenarios_advance"],
                "total_scenarios": sc["total_scenarios"],
                "advance_pct": round(sc["scenarios_advance"] / max(sc["total_scenarios"], 1) * 100, 1),
                "status": status,
                "detail": detail,
            })

        remaining_out = [{
            "match_id": m.id,
            "home_code": m.home_code,
            "home_name": names.get(m.home_code, m.home_code),
            "away_code": m.away_code,
            "away_name": names.get(m.away_code, m.away_code),
            "kickoff": iso_utc(m.kickoff),
        } for m in remaining]

        output.append({
            "group": g,
            "matches_remaining": len(remaining),
            "remaining_fixtures": remaining_out,
            "teams": teams_out,
        })

    return output
