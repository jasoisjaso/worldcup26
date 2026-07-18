"""Tournament-wide awards computed from the persistent archive.

Every award is derived from tables we already populate:
  - PlayerTournamentStats (goals, assists, minutes, cards)
  - TeamSeasonStats (wins, goals, xG, clean sheets, cards)
  - MatchEvent (every goal, card, sub)
  - MatchStatistics (shots, saves, possession)
  - Match (scores, status, ELO for upset detection)

Returns a single JSON payload with all award categories.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from backend.db.session import get_db
from backend.db.models import (
    Match, Team, PlayerTournamentStats, TeamSeasonStats,
    MatchEvent, MatchStatistics,
)

router = APIRouter()


def _team_dict(db: Session, code: str) -> dict:
    t = db.get(Team, code)
    if not t:
        return {"code": code, "name": code, "flag_url": None, "primary_color": None}
    return {
        "code": t.code, "name": t.name,
        "flag_url": t.flag_url, "primary_color": t.primary_color,
    }


@router.get("/awards")
def get_awards(db: Session = Depends(get_db)):
    return _compute_awards(db)


def _compute_awards(db: Session) -> dict:
    awards: dict = {}

    # ── 1. Golden Boot ──────────────────────────────────────────────
    top_scorers = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.tournament == "WC2026")
        .filter(PlayerTournamentStats.goals > 0)
        .order_by(
            desc(PlayerTournamentStats.goals),
            desc(PlayerTournamentStats.assists),
            PlayerTournamentStats.minutes.asc(),
        )
        .limit(5)
        .all()
    )
    awards["golden_boot"] = [{
        "player_name": p.player_name, "team_name": p.team_name,
        "goals": p.goals, "assists": p.assists, "minutes": p.minutes,
        "penalty_goals": p.penalty_goals, "appearances": p.appearances,
    } for p in top_scorers]

    # ── 2. Most Assists ─────────────────────────────────────────────
    top_assists = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.tournament == "WC2026")
        .filter(PlayerTournamentStats.assists > 0)
        .order_by(desc(PlayerTournamentStats.assists), desc(PlayerTournamentStats.goals))
        .limit(5)
        .all()
    )
    awards["most_assists"] = [{
        "player_name": p.player_name, "team_name": p.team_name,
        "assists": p.assists, "goals": p.goals, "minutes": p.minutes,
        "appearances": p.appearances,
    } for p in top_assists]

    # ── 3. Golden Glove (team-level saves) ──────────────────────────
    # MatchStatistics is per-team per-match. Sum saves by team.
    keeper_rows = (
        db.query(
            MatchStatistics.team_name,
            func.sum(MatchStatistics.goalkeeper_saves).label("saves"),
            func.count(MatchStatistics.id).label("games"),
        )
        .group_by(MatchStatistics.team_name)
        .having(func.sum(MatchStatistics.goalkeeper_saves) > 0)
        .order_by(desc("saves"))
        .limit(5)
        .all()
    )
    awards["golden_glove"] = [{
        "team_name": r.team_name, "saves": int(r.saves), "games": int(r.games),
    } for r in keeper_rows]

    # ── 4. Most Cards (team) ────────────────────────────────────────
    card_teams = (
        db.query(TeamSeasonStats)
        .filter(TeamSeasonStats.matches_played > 0)
        .order_by(
            desc(TeamSeasonStats.red_cards * 3 + TeamSeasonStats.yellow_cards),
        )
        .limit(5)
        .all()
    )
    awards["most_cards"] = [{
        "team_name": t.team_name, "team_code": t.team_code,
        "yellow_cards": t.yellow_cards, "red_cards": t.red_cards,
        "card_points": t.red_cards * 3 + t.yellow_cards,
    } for t in card_teams]

    # ── 5. Fair Play Award (fewest cards, min 3 matches) ────────────
    fair_play = (
        db.query(TeamSeasonStats)
        .filter(TeamSeasonStats.matches_played >= 3)
        .order_by(
            (TeamSeasonStats.red_cards * 3 + TeamSeasonStats.yellow_cards).asc(),
        )
        .limit(5)
        .all()
    )
    awards["fair_play"] = [{
        "team_name": t.team_name, "team_code": t.team_code,
        "yellow_cards": t.yellow_cards, "red_cards": t.red_cards,
        "card_points": t.red_cards * 3 + t.yellow_cards,
        "matches_played": t.matches_played,
    } for t in fair_play]

    # ── 6. Best Team (standout — points, GD, GF) ────────────────────
    all_teams = db.query(TeamSeasonStats).filter(TeamSeasonStats.matches_played > 0).all()
    best_sorted = sorted(all_teams, key=lambda t: (
        t.wins * 3 + t.draws,
        t.goals_for - t.goals_against,
        t.goals_for,
    ), reverse=True)
    awards["best_team"] = [{
        "team_name": t.team_name, "team_code": t.team_code,
        "matches_played": t.matches_played, "wins": t.wins, "draws": t.draws, "losses": t.losses,
        "goals_for": t.goals_for, "goals_against": t.goals_against,
        "gd": t.goals_for - t.goals_against, "clean_sheets": t.clean_sheets,
        "points": t.wins * 3 + t.draws,
        **_team_dict(db, t.team_code),
    } for t in best_sorted[:5]]

    # ── 7. Top Scoring Team ─────────────────────────────────────────
    awards["top_scoring_team"] = [{
        "team_name": t.team_name, "team_code": t.team_code,
        "goals_for": t.goals_for, "matches_played": t.matches_played,
        "goals_per_game": round(t.goals_for / t.matches_played, 2) if t.matches_played else 0,
    } for t in sorted(all_teams, key=lambda t: t.goals_for, reverse=True)[:5]]

    # ── 8. Biggest Upset (ELO gap, KO matches only) ─────────────────
    upsets: list[dict] = []
    ko_matches = (
        db.query(Match)
        .filter(Match.status == "complete", Match.matchday >= 4)
        .all()
    )
    for m in ko_matches:
        if m.home_score is None or m.away_score is None:
            continue
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if not home or not away:
            continue
        # Determine winner (shootout-aware)
        if m.home_score > m.away_score:
            winner, loser = home, away
        elif m.away_score > m.home_score:
            winner, loser = away, home
        else:
            # Level aggregate — shootout decides
            if m.shootout_home_score is not None and m.shootout_away_score is not None:
                if m.shootout_home_score > m.shootout_away_score:
                    winner, loser = home, away
                elif m.shootout_away_score > m.shootout_home_score:
                    winner, loser = away, home
                else:
                    continue
            else:
                continue
        gap = (loser.elo or 1500) - (winner.elo or 1500)
        if gap > 0:
            upsets.append({
                "match_id": m.id,
                "winner": winner.name, "winner_code": winner.code,
                "loser": loser.name, "loser_code": loser.code,
                "elo_gap": round(gap, 0),
                "score": f"{m.home_score}-{m.away_score}",
                "venue": m.venue,
            })
    upsets.sort(key=lambda u: u["elo_gap"], reverse=True)
    awards["biggest_upset"] = upsets[:5]

    # ── 9. Match of the Tournament (drama score) ────────────────────
    # Drama score = total_goals*1 + had_pens*5 + had_red*2 + was_upset*3
    # Computed from Match + MatchEvent per completed match.
    drama_matches: list[dict] = []
    for m in ko_matches:
        if m.home_score is None or m.away_score is None:
            continue
        total_goals = (m.home_score or 0) + (m.away_score or 0)
        went_pens = 1 if (m.shootout_home_score is not None) else 0
        # Count red cards from events
        reds = db.query(MatchEvent).filter(
            MatchEvent.match_id == m.id,
            MatchEvent.detail.like("%Red%"),
        ).count()
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        # Upset bonus: winner had lower ELO
        upset_bonus = 0
        if home and away:
            if m.home_score > m.away_score and (away.elo or 1500) > (home.elo or 1500):
                upset_bonus = 3
            elif m.away_score > m.home_score and (home.elo or 1500) > (away.elo or 1500):
                upset_bonus = 3
        drama = total_goals * 1 + went_pens * 5 + reds * 2 + upset_bonus
        if drama >= 3:  # only show matches with some drama
            drama_matches.append({
                "match_id": m.id,
                "home": home.name if home else m.home_code,
                "away": away.name if away else m.away_code,
                "home_code": m.home_code, "away_code": m.away_code,
                "score": f"{m.home_score}-{m.away_score}",
                "went_to_pens": bool(went_pens),
                "red_cards": reds,
                "total_goals": total_goals,
                "drama_score": drama,
            })
    drama_matches.sort(key=lambda d: d["drama_score"], reverse=True)
    awards["match_of_tournament"] = drama_matches[:5]

    # ── 10. Most Disappointing Team ─────────────────────────────────
    # Team with highest pre-tournament ELO that didn't reach QF (matchday < 6).
    all_team_codes = {t.code: t for t in db.query(Team).all()}
    # Find teams that only played matchdays 1-5 (group + R32 + R16, no QF+)
    team_max_md: dict[str, int] = {}
    for m in db.query(Match).filter(Match.status == "complete").all():
        for code in (m.home_code, m.away_code):
            if code:
                team_max_md[code] = max(team_max_md.get(code, 0), m.matchday or 0)
    disappointments: list[dict] = []
    for code, max_md in team_max_md.items():
        if max_md < 6 and code in all_team_codes:  # didn't reach QF
            t = all_team_codes[code]
            ts = next((ts for ts in all_teams if ts.team_code == code), None)
            disappointments.append({
                "team_name": t.name, "team_code": code,
                "elo": t.elo or 1500,
                "max_round_reached": max_md,
                "matches_played": ts.matches_played if ts else 0,
                "wins": ts.wins if ts else 0,
                **_team_dict(db, code),
            })
    disappointments.sort(key=lambda d: d["elo"], reverse=True)
    awards["most_disappointing"] = disappointments[:5]

    # ── Tournament status ───────────────────────────────────────────
    total_complete = db.query(Match).filter(Match.status == "complete").count()
    final = db.get(Match, "M104")
    final_complete = final is not None and final.status == "complete"
    champion = None
    if final_complete and final is not None and final.home_score is not None and final.away_score is not None:
        if final.home_score > final.away_score:
            champ_code = final.home_code
        elif final.away_score > final.home_score:
            champ_code = final.away_code
        elif final.shootout_home_score is not None and final.shootout_away_score is not None:
            champ_code = final.home_code if final.shootout_home_score > final.shootout_away_score else final.away_code
        else:
            champ_code = None
        if champ_code:
            champion = _team_dict(db, champ_code)
            champion["score"] = f"{final.home_score}-{final.away_score}"
            if final.shootout_home_score is not None:
                champion["shootout"] = f"{final.shootout_home_score}-{final.shootout_away_score}"

    awards["_meta"] = {
        "matches_complete": total_complete,
        "final_complete": final_complete,
        "champion": champion,
    }

    return awards
