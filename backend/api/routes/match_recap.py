"""Per-match recap — everything a user wants to know AFTER a match finishes
(or while it's running). Pure DB read, zero API quota cost.

Joins MatchEvent (goals + cards + subs) + MatchStatistics (possession / shots /
xG / corners / fouls / offsides / saves / pass%) + MatchLineup + MatchLineupPlayer
(starting XI + bench + formation) for both teams, plus an auto-picked Man of
the Match (top scorer, assists used as tie-breaker).

Designed so the /match/{id} page never needs the user to hunt for a stat —
every "what happened?" answer lives in this payload.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import (
    Match, MatchEvent, MatchStatistics, MatchLineup, MatchLineupPlayer, Team,
)
from backend.data.fetchers.injuries import TEAM_IDS
from backend.util.datetime import iso_utc

router = APIRouter()


def _team_api_id(code: str | None) -> int | None:
    if not code:
        return None
    return TEAM_IDS.get(code.lower())


@router.get("/{match_id}/recap")
def match_recap(match_id: str, db: Session = Depends(get_db)):
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise HTTPException(404, "match not found")

    home_team = db.query(Team).filter(Team.code == m.home_code).first() if m.home_code else None
    away_team = db.query(Team).filter(Team.code == m.away_code).first() if m.away_code else None
    home_api = _team_api_id(m.home_code)
    away_api = _team_api_id(m.away_code)

    def side_of(team_id):
        if team_id and team_id == home_api: return "home"
        if team_id and team_id == away_api: return "away"
        return None

    # Events
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.elapsed.asc(), MatchEvent.id.asc())
        .all()
    )
    # VAR-disallowed goal index. api-football emits a 'Var' event at the same
    # minute / same player as the original 'Goal' when VAR overturns it. We
    # capture the REASON (e.g. 'Foul', 'Offside') from the Var event detail so
    # the FE can render "VAR — Goal disallowed for foul" rather than a generic
    # marker. A user who didn't watch the game can now read the timeline and
    # know exactly what happened on the VAR review.
    disallowed: dict[tuple, str] = {}
    for e in events:
        if e.type == "Var" and e.detail and (
            "disallowed" in e.detail.lower()
            or "cancelled" in e.detail.lower()
            or "canceled" in e.detail.lower()
        ) and e.player_id and e.elapsed is not None:
            # api-football: "Goal Disallowed - Foul" / "Goal Disallowed - offside" etc.
            reason = e.detail
            if " - " in reason:
                reason = reason.split(" - ", 1)[1].strip()
            else:
                reason = "VAR review"
            disallowed[(e.elapsed, e.player_id)] = reason

    events_out = [
        {
            "minute": (e.elapsed or 0) + (e.extra or 0),
            "elapsed": e.elapsed,
            "extra": e.extra,
            "type": e.type,
            "detail": e.detail,
            "player_id": e.player_id,
            "player_name": e.player_name,
            "assist_name": e.assist_name,
            "team_side": side_of(e.team_id),
            "team_name": e.team_name,
            "var_disallowed": (
                e.type == "Goal"
                and e.elapsed is not None
                and (e.elapsed, e.player_id) in disallowed
            ),
            # Human-readable reason from the Var event detail when this goal
            # was VAR-disallowed. None when no VAR ruling applies.
            "var_reason": (
                disallowed.get((e.elapsed, e.player_id))
                if e.type == "Goal" and e.elapsed is not None else None
            ),
        }
        for e in events
    ]

    # Stats per team — return None if MatchStatistics doesn't have a row yet.
    def stats_for(team_api):
        if not team_api:
            return None
        s = (
            db.query(MatchStatistics)
            .filter(MatchStatistics.match_id == match_id)
            .filter(MatchStatistics.team_id == team_api)
            .first()
        )
        if not s:
            return None
        return {
            "possession_pct": s.ball_possession,
            "shots_total": s.total_shots,
            "shots_on_target": s.shots_on_goal,
            "shots_off_target": s.shots_off_goal,
            "shots_blocked": s.blocked_shots,
            "shots_inside_box": s.shots_inside_box,
            "shots_outside_box": s.shots_outside_box,
            "corners": s.corner_kicks,
            "fouls": s.fouls,
            "offsides": s.offsides,
            "yellow_cards": s.yellow_cards,
            "red_cards": s.red_cards,
            "saves": s.goalkeeper_saves,
            "passes_total": s.total_passes,
            "passes_accurate": s.passes_accurate,
            "passes_pct": s.passes_pct,
            "xg": s.expected_goals,
        }

    def lineup_for(team_api):
        if not team_api:
            return None
        lu = (
            db.query(MatchLineup)
            .filter(MatchLineup.match_id == match_id)
            .filter(MatchLineup.team_id == team_api)
            .first()
        )
        if not lu:
            return None
        players = (
            db.query(MatchLineupPlayer)
            .filter(MatchLineupPlayer.lineup_id == lu.id)
            .all()
        )
        return {
            "formation": lu.formation,
            "coach": lu.coach_name,
            "starters": [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "number": p.number,
                    "position": p.position,
                    "grid": p.grid,
                }
                for p in players if p.is_starter
            ],
            "bench": [
                {
                    "player_id": p.player_id,
                    "player_name": p.player_name,
                    "number": p.number,
                    "position": p.position,
                }
                for p in players if not p.is_starter
            ],
        }

    # Man of the match — most goals, assists tie-break. Skip "Own Goal"
    # and "Missed Penalty" (both arrive as type="Goal" from api-football).
    # VAR-disallowed goals are also excluded (the `disallowed` set above is
    # keyed by (elapsed, player_id) and is built once at the top of this
    # handler). Without this filter, Vinicius's VAR-overturned goal vs
    # Scotland was inflating his match goal count by one in the in-match
    # top performer panel.
    goal_counts: dict = {}
    assist_counts: dict = {}
    # Dedup the same way the tournament-stats rebuild does: api-football
    # sometimes re-emits the same goal with a slightly adjusted minute
    # (e.g. 45+3' becomes 48' in their reconciled stats run). We track
    # (player_id -> [absolute_minutes_already_counted]) and skip any goal
    # whose minute is within 3 of one already counted.
    seen_by_player: dict[int, list[int]] = {}
    for e in events:
        if (
            e.type == "Goal"
            and e.player_name
            and e.detail != "Own Goal"
            and e.detail != "Missed Penalty"
            and not (
                e.player_id is not None
                and e.elapsed is not None
                and (e.elapsed, e.player_id) in disallowed
            )
        ):
            mins = (e.elapsed or 0) + (e.extra or 0)
            if e.player_id is not None:
                seen = seen_by_player.setdefault(e.player_id, [])
                if any(abs(mins - s) <= 3 for s in seen):
                    continue
                seen.append(mins)
            key = (e.player_name, e.player_id, side_of(e.team_id))
            goal_counts[key] = goal_counts.get(key, 0) + 1
            if e.assist_name:
                assist_counts[e.assist_name] = assist_counts.get(e.assist_name, 0) + 1
    motm = None
    if goal_counts:
        (name, pid, side), goals = max(
            goal_counts.items(),
            key=lambda x: (x[1], assist_counts.get(x[0][0], 0)),
        )
        motm = {
            "player_id": pid,
            "name": name,
            "goals": goals,
            "side": side,
            "team_name": home_team.name if side == "home" and home_team else (away_team.name if side == "away" and away_team else None),
        }

    def team_block(code, team, api_id):
        return {
            "code": code,
            "name": team.name if team else ((code or "").upper()),
            "flag_url": team.flag_url if team else None,
            "stats": stats_for(api_id),
            "lineup": lineup_for(api_id),
        }

    has_events = bool(events_out)
    has_stats = (stats_for(home_api) is not None) or (stats_for(away_api) is not None)

    # Shootout score (knockout matches decided on penalties). NULL otherwise.
    # When set, the FE renders the (X-Y pens) suffix on the recap header score
    # and shows the dot-row shootout breakdown (same component used live).
    shootout_score = (
        {"home": m.shootout_home_score, "away": m.shootout_away_score}
        if m.shootout_home_score is not None or m.shootout_away_score is not None
        else None
    )

    return {
        "match_id": match_id,
        "status": m.status,
        "is_complete": m.status == "complete",
        "has_content": has_events or has_stats,
        "score": {"home": m.home_score, "away": m.away_score} if m.home_score is not None else None,
        "shootout_score": shootout_score,
        "kickoff": iso_utc(m.kickoff),
        "venue": m.venue,
        "home": team_block(m.home_code, home_team, home_api),
        "away": team_block(m.away_code, away_team, away_api),
        "events": events_out,
        "motm": motm,
    }
