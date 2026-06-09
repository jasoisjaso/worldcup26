"""Match 3 Watch: flags matchday-3 games where a team's group fate is already settled.

A team whose qualification is sealed (or elimination confirmed) before their third
group game is likely to rotate their squad. Bookmakers are slow to adjust for this.
Historical pattern: backing the team that still needs a result in Match 3 returned
+12.8% ROI over the last two World Cups.
"""
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import Match, Team

router = APIRouter()


def _compute_points(matches: list[Match], team_code: str) -> int:
    pts = 0
    for m in matches:
        if m.status != "complete":
            continue
        if m.home_code == team_code:
            if m.home_score is None or m.away_score is None:
                continue
            if m.home_score > m.away_score:
                pts += 3
            elif m.home_score == m.away_score:
                pts += 1
        elif m.away_code == team_code:
            if m.home_score is None or m.away_score is None:
                continue
            if m.away_score > m.home_score:
                pts += 3
            elif m.home_score == m.away_score:
                pts += 1
    return pts


def _max_possible(matches: list[Match], team_code: str) -> int:
    remaining = sum(
        1 for m in matches
        if m.status == "upcoming" and (m.home_code == team_code or m.away_code == team_code)
    )
    return _compute_points(matches, team_code) + remaining * 3


@router.get("")
def get_match3_alerts(db: Session = Depends(get_db)):
    all_matches = db.query(Match).all()

    groups: dict[str, list[Match]] = defaultdict(list)
    for m in all_matches:
        groups[m.group].append(m)

    alerts = []

    for group, matches in groups.items():
        # find matchday-3 games
        md3_games = [m for m in matches if m.matchday == 3 and m.status == "upcoming"]
        if not md3_games:
            continue

        # collect all team codes in this group
        teams_in_group: set[str] = set()
        for m in matches:
            teams_in_group.add(m.home_code)
            teams_in_group.add(m.away_code)

        # compute current points and max possible for each team
        points = {t: _compute_points(matches, t) for t in teams_in_group}
        max_pts = {t: _max_possible(matches, t) for t in teams_in_group}

        # top 2 per group qualify; check if any team is already safe or eliminated
        sorted_by_pts = sorted(teams_in_group, key=lambda t: points[t], reverse=True)
        pts_values = sorted(points.values(), reverse=True)

        # a team is safe if even the 3rd-place team can't overtake them
        safe_teams: set[str] = set()
        if len(pts_values) >= 3:
            third_max = max(max_pts[t] for t in sorted_by_pts[2:])
            for t in sorted_by_pts[:2]:
                if points[t] > third_max:
                    safe_teams.add(t)

        # a team is eliminated if even their max points won't reach current 2nd place
        eliminated_teams: set[str] = set()
        if len(pts_values) >= 2:
            second_current = pts_values[1]
            for t in sorted_by_pts[2:]:
                if max_pts[t] < second_current:
                    eliminated_teams.add(t)

        for game in md3_games:
            home_safe = game.home_code in safe_teams
            away_safe = game.away_code in safe_teams
            home_out = game.home_code in eliminated_teams
            away_out = game.away_code in eliminated_teams

            if not (home_safe or away_safe or home_out or away_out):
                continue

            home_team = db.get(Team, game.home_code)
            away_team = db.get(Team, game.away_code)
            home_name = home_team.name if home_team else game.home_code
            away_name = away_team.name if away_team else game.away_code

            rotation_team = None
            needs_result_team = None

            if home_safe or home_out:
                rotation_team = home_name
                needs_result_team = away_name
            elif away_safe or away_out:
                rotation_team = away_name
                needs_result_team = home_name

            if rotation_team:
                status_label = "already qualified" if (home_safe or away_safe) else "already eliminated"
                alerts.append({
                    "match_id": game.id,
                    "group": group,
                    "kickoff": game.kickoff.isoformat() if game.kickoff else None,
                    "match_label": f"{home_name} vs {away_name}",
                    "rotation_team": rotation_team,
                    "rotation_status": status_label,
                    "needs_result_team": needs_result_team,
                    "warning": (
                        f"{rotation_team} is {status_label} -- squad rotation likely. "
                        f"Odds may not yet reflect this. {needs_result_team} still need a result."
                    ),
                })

    return alerts
