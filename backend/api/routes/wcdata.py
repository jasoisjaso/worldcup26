"""Public read API over the persistent archive.

Surface everything we've persisted from api-football so it's queryable without
hitting their API. Designed to grow into a standalone WC2026 data service.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import (
    ApiFootballPrediction,
    Match,
    MatchEvent,
    MatchH2H,
    MatchLineup,
    MatchLineupPlayer,
    MatchStatistics,
    PlayerProfile,
    PlayerTournamentStats,
    Team,
    TeamSeasonStats,
)
from backend.db.session import get_db

router = APIRouter()


@router.get("/archive/summary")
def archive_summary(db: Session = Depends(get_db)):
    """Counts across the persistent archive — useful for monitoring growth."""
    return {
        "match_events": db.query(MatchEvent).count(),
        "match_lineups": db.query(MatchLineup).count(),
        "match_lineup_players": db.query(MatchLineupPlayer).count(),
        "match_statistics": db.query(MatchStatistics).count(),
        "match_statistics_final": db.query(MatchStatistics).filter(MatchStatistics.is_final == True).count(),
        "api_football_predictions": db.query(ApiFootballPrediction).count(),
        "match_h2h": db.query(MatchH2H).count(),
        "player_profiles": db.query(PlayerProfile).count(),
        "player_tournament_stats": db.query(PlayerTournamentStats).count(),
        "team_season_stats": db.query(TeamSeasonStats).count(),
    }


@router.get("/events/{match_id}")
def match_events(match_id: str, db: Session = Depends(get_db)):
    """Every persisted event for a match, ordered by minute."""
    rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.elapsed.asc(), MatchEvent.extra.asc().nullsfirst(), MatchEvent.id.asc())
        .all()
    )
    return {
        "match_id": match_id,
        "count": len(rows),
        "events": [{
            "elapsed": r.elapsed, "extra": r.extra,
            "type": r.type, "detail": r.detail,
            "player_id": r.player_id, "player_name": r.player_name,
            "assist_id": r.assist_id, "assist_name": r.assist_name,
            "team_id": r.team_id, "team_name": r.team_name,
            "comments": r.comments,
        } for r in rows],
    }


@router.get("/lineups/{match_id}")
def match_lineups(match_id: str, db: Session = Depends(get_db)):
    """Confirmed lineups for both teams, with players."""
    lineups = db.query(MatchLineup).filter(MatchLineup.match_id == match_id).all()
    out = []
    for l in lineups:
        players = (
            db.query(MatchLineupPlayer)
            .filter(MatchLineupPlayer.lineup_id == l.id)
            .order_by(MatchLineupPlayer.is_starter.desc(), MatchLineupPlayer.number.asc())
            .all()
        )
        out.append({
            "team_id": l.team_id, "team_name": l.team_name,
            "formation": l.formation,
            "coach_id": l.coach_id, "coach_name": l.coach_name,
            "starters": [{
                "player_id": p.player_id, "name": p.player_name,
                "number": p.number, "position": p.position, "grid": p.grid,
            } for p in players if p.is_starter],
            "substitutes": [{
                "player_id": p.player_id, "name": p.player_name,
                "number": p.number, "position": p.position,
            } for p in players if not p.is_starter],
        })
    return {"match_id": match_id, "lineups": out}


@router.get("/statistics/{match_id}")
def match_statistics(match_id: str, db: Session = Depends(get_db)):
    """Per-team stats snapshot. is_final=True means this is the FT total."""
    rows = db.query(MatchStatistics).filter(MatchStatistics.match_id == match_id).all()
    return {
        "match_id": match_id,
        "teams": [{
            "team_id": r.team_id, "team_name": r.team_name,
            "is_final": r.is_final, "captured_at": r.captured_at.isoformat() if r.captured_at else None,
            "shots_on_goal": r.shots_on_goal, "shots_off_goal": r.shots_off_goal,
            "total_shots": r.total_shots, "blocked_shots": r.blocked_shots,
            "shots_inside_box": r.shots_inside_box, "shots_outside_box": r.shots_outside_box,
            "fouls": r.fouls, "corner_kicks": r.corner_kicks, "offsides": r.offsides,
            "ball_possession": r.ball_possession,
            "yellow_cards": r.yellow_cards, "red_cards": r.red_cards,
            "goalkeeper_saves": r.goalkeeper_saves,
            "total_passes": r.total_passes, "passes_accurate": r.passes_accurate,
            "passes_pct": r.passes_pct, "expected_goals": r.expected_goals,
        } for r in rows],
    }


@router.get("/predictions/{match_id}")
def api_prediction(match_id: str, db: Session = Depends(get_db)):
    """api-football's own pre-match prediction snapshot."""
    p = (
        db.query(ApiFootballPrediction)
        .filter(ApiFootballPrediction.match_id == match_id)
        .first()
    )
    if not p:
        raise HTTPException(404, "no prediction snapshot for this match")
    return {
        "match_id": p.match_id,
        "winner_name": p.winner_name, "winner_comment": p.winner_comment,
        "advice": p.advice, "win_or_draw": p.win_or_draw, "under_over": p.under_over,
        "goals_home_avg": p.goals_home, "goals_away_avg": p.goals_away,
        "pct": {"home": p.pct_home, "draw": p.pct_draw, "away": p.pct_away},
        "comparison": {
            "form": {"home": p.comp_form_home, "away": p.comp_form_away},
            "att":  {"home": p.comp_att_home, "away": p.comp_att_away},
            "def":  {"home": p.comp_def_home, "away": p.comp_def_away},
            "poisson": {"home": p.comp_poisson_home, "away": p.comp_poisson_away},
            "h2h":  {"home": p.comp_h2h_home, "away": p.comp_h2h_away},
            "goals": {"home": p.comp_goals_home, "away": p.comp_goals_away},
            "total": {"home": p.comp_total_home, "away": p.comp_total_away},
        },
        "captured_at": p.captured_at.isoformat() if p.captured_at else None,
    }


@router.get("/h2h/{team1_code}/{team2_code}")
def h2h(team1_code: str, team2_code: str, db: Session = Depends(get_db)):
    """Historical head-to-head between two WC teams (by code, e.g. /h2h/arg/bra)."""
    hid = TEAM_IDS.get(team1_code.lower())
    aid = TEAM_IDS.get(team2_code.lower())
    if not hid or not aid:
        raise HTTPException(404, "unknown team code")
    t1, t2 = (hid, aid) if hid < aid else (aid, hid)
    rows = (
        db.query(MatchH2H)
        .filter(MatchH2H.team1_id == t1, MatchH2H.team2_id == t2)
        .order_by(desc(MatchH2H.fixture_date))
        .all()
    )
    return {
        "team1": team1_code, "team2": team2_code,
        "count": len(rows),
        "matches": [{
            "date": r.fixture_date.isoformat() if r.fixture_date else None,
            "league": r.league_name, "season": r.season,
            "home": r.home_team_name, "away": r.away_team_name,
            "home_score": r.home_score, "away_score": r.away_score,
            "status": r.status_short,
        } for r in rows],
    }


@router.get("/players/top")
def players_top(
    metric: str = "goals",
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """Top players by goals/assists/cards from the persistent archive.
    Zero API cost — pulls from PlayerTournamentStats which is rebuilt after each FT."""
    valid_metrics = {"goals", "assists", "yellow_cards", "red_cards", "appearances"}
    if metric not in valid_metrics:
        raise HTTPException(400, f"metric must be one of {sorted(valid_metrics)}")

    col = getattr(PlayerTournamentStats, metric)
    rows = (
        db.query(PlayerTournamentStats)
        .filter(col > 0)
        .order_by(desc(col), PlayerTournamentStats.player_name.asc())
        .limit(limit)
        .all()
    )
    return {
        "metric": metric, "count": len(rows),
        "players": [{
            "player_id": r.player_id, "name": r.player_name,
            "team_id": r.team_id, "team_name": r.team_name,
            "goals": r.goals, "assists": r.assists,
            "yellow_cards": r.yellow_cards, "red_cards": r.red_cards,
            "penalty_goals": r.penalty_goals, "own_goals": r.own_goals,
        } for r in rows],
    }


@router.get("/players/{player_id}")
def player_profile(player_id: int, db: Session = Depends(get_db)):
    """Full player profile + WC tournament stats."""
    p = db.query(PlayerProfile).filter(PlayerProfile.player_id == player_id).first()
    stats = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == player_id)
        .first()
    )
    return {
        "profile": {
            "player_id": p.player_id, "name": p.name,
            "firstname": p.firstname, "lastname": p.lastname,
            "age": p.age, "birth_date": p.birth_date,
            "birth_place": p.birth_place, "birth_country": p.birth_country,
            "nationality": p.nationality, "height": p.height, "weight": p.weight,
            "photo_url": p.photo_url, "position": p.position,
            "team_id": p.team_id, "team_name": p.team_name,
        } if p else None,
        "tournament_stats": {
            "appearances": stats.appearances, "minutes": stats.minutes,
            "goals": stats.goals, "assists": stats.assists,
            "yellow_cards": stats.yellow_cards, "red_cards": stats.red_cards,
            "penalty_goals": stats.penalty_goals, "own_goals": stats.own_goals,
        } if stats else None,
    }


@router.get("/teams/{team_code}/season")
def team_season(team_code: str, db: Session = Depends(get_db)):
    """Per-team accumulated WC stats — wins, GF/GA, xG, possession, etc."""
    code = team_code.lower()
    row = (
        db.query(TeamSeasonStats)
        .filter(TeamSeasonStats.team_code == code)
        .first()
    )
    team = db.query(Team).filter(Team.code == code).first()
    if not row:
        return {
            "team_code": code,
            "team_name": team.name if team else None,
            "matches_played": 0,
            "season_stats": None,
        }
    return {
        "team_code": row.team_code, "team_name": row.team_name,
        "team_id": row.team_id,
        "matches_played": row.matches_played,
        "wins": row.wins, "draws": row.draws, "losses": row.losses,
        "goals_for": row.goals_for, "goals_against": row.goals_against,
        "goal_difference": row.goals_for - row.goals_against,
        "xg_for": round(row.xg_for or 0, 2),
        "xg_against": round(row.xg_against or 0, 2),
        "xg_diff": round((row.xg_for or 0) - (row.xg_against or 0), 2),
        "possession_avg": round(row.possession_avg, 1) if row.possession_avg else None,
        "shots_total": row.shots_total, "shots_on_target": row.shots_on_target,
        "fouls": row.fouls,
        "yellow_cards": row.yellow_cards, "red_cards": row.red_cards,
        "clean_sheets": row.clean_sheets,
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }


@router.get("/teams/season/all")
def teams_season_all(db: Session = Depends(get_db)):
    """All teams' WC season stats — useful for a tournament-wide form table."""
    rows = db.query(TeamSeasonStats).order_by(
        desc(TeamSeasonStats.wins),
        desc(TeamSeasonStats.goals_for - TeamSeasonStats.goals_against),
        desc(TeamSeasonStats.goals_for),
    ).all()
    return {
        "count": len(rows),
        "teams": [{
            "team_code": r.team_code, "team_name": r.team_name,
            "matches_played": r.matches_played,
            "wins": r.wins, "draws": r.draws, "losses": r.losses,
            "goals_for": r.goals_for, "goals_against": r.goals_against,
            "xg_for": round(r.xg_for or 0, 2),
            "xg_against": round(r.xg_against or 0, 2),
            "possession_avg": round(r.possession_avg, 1) if r.possession_avg else None,
            "clean_sheets": r.clean_sheets,
        } for r in rows],
    }
