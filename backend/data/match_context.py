"""Composite pre-match context payload — everything a user needs to decide
a bet without leaving the match page.

Pulls from data we already have: form rows from Match table, season averages
from FixtureArchive (via team_season_aggregates), head-to-head from MatchH2H,
absences from the suspensions override file, stakes derived from group
position math. Pure DB reads — no API calls.

Synchronous on purpose: the caller route handler is async and adds the
model-swing-from-absences calculation on top (which IS async because it
needs to run the prediction pipeline twice). Keeping the heavy compose
sync makes it cheap to unit-test in isolation.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.data.fetchers.injuries import TEAM_IDS
from backend.data.fetchers.suspensions import get_suspension_count
from backend.data.team_season_aggregates import season_aggregates
from backend.db.models import Match, MatchH2H, Team


# Goals-per-match and conceded-per-match are easier to compute from Match
# results (our authoritative scoreline source) than from FixtureArchive
# (which only has fixtures the harvester has touched).
def _team_match_results(db: Session, team_code: str, limit: int = 38) -> list[Match]:
    return (
        db.query(Match)
        .filter(or_(Match.home_code == team_code, Match.away_code == team_code))
        .filter(Match.status == "complete")
        .filter(Match.home_score.isnot(None))
        .order_by(Match.kickoff.desc())
        .limit(limit)
        .all()
    )


def _scoring_stats(db: Session, team_code: str) -> dict:
    """Goals-for / goals-against / BTTS% / clean-sheet% from real results."""
    rows = _team_match_results(db, team_code)
    if not rows:
        return {
            "matches_sampled": 0,
            "goals_per_match": None,
            "conceded_per_match": None,
            "btts_pct": None,
            "cs_pct": None,
        }
    n = len(rows)
    gf = ga = btts = cs = 0
    for m in rows:
        if m.home_code == team_code:
            gf += m.home_score or 0
            ga += m.away_score or 0
        else:
            gf += m.away_score or 0
            ga += m.home_score or 0
        if (m.home_score or 0) > 0 and (m.away_score or 0) > 0:
            btts += 1
        # Clean sheet = the OPPONENT scored zero in this match
        opp_score = (m.away_score if m.home_code == team_code else m.home_score) or 0
        if opp_score == 0:
            cs += 1
    return {
        "matches_sampled": n,
        "goals_per_match": round(gf / n, 2),
        "conceded_per_match": round(ga / n, 2),
        "btts_pct": round(btts / n, 2),
        "cs_pct": round(cs / n, 2),
    }


def _recent_form(db: Session, team_code: str, n: int = 5) -> list[dict]:
    """Last N completed matches as form rows. Oldest → newest for left-to-right reading."""
    rows = _team_match_results(db, team_code, limit=n)
    # Pre-fetch opponent names — same pattern as /teams/{code}/recent-form
    opp_codes = {
        (m.away_code if m.home_code == team_code else m.home_code) for m in rows
    }
    opp_names = (
        {t.code: t.name for t in db.query(Team).filter(Team.code.in_(opp_codes)).all()}
        if opp_codes else {}
    )

    def _result(m: Match) -> Optional[str]:
        if m.home_score is None or m.away_score is None:
            return None
        is_home = m.home_code == team_code
        mine = m.home_score if is_home else m.away_score
        theirs = m.away_score if is_home else m.home_score
        if mine > theirs:
            return "W"
        if mine < theirs:
            return "L"
        return "D"

    out = []
    for m in rows:
        opp = m.away_code if m.home_code == team_code else m.home_code
        out.append({
            "match_id": m.id,
            "opponent_code": opp,
            "opponent_name": opp_names.get(opp, opp.upper()),
            "score": f"{m.home_score}-{m.away_score}",
            "result": _result(m),
            "kickoff": m.kickoff.isoformat() if m.kickoff else None,
            "venue": "H" if m.home_code == team_code else "A",
        })
    return list(reversed(out))


def _h2h_summary(db: Session, home_code: str, away_code: str) -> dict:
    """Lifetime H2H record from the home team's perspective. Reads MatchH2H."""
    home_api = TEAM_IDS.get(home_code)
    away_api = TEAM_IDS.get(away_code)
    if not home_api or not away_api:
        return _empty_h2h()
    t1, t2 = sorted([home_api, away_api])
    rows = (
        db.query(MatchH2H)
        .filter(MatchH2H.team1_id == t1, MatchH2H.team2_id == t2)
        .order_by(MatchH2H.fixture_date.desc())
        .all()
    )
    if not rows:
        return _empty_h2h()

    home_wins = away_wins = draws = goals = 0
    last_str = None
    for r in rows:
        hg, ag = r.home_score or 0, r.away_score or 0
        goals += hg + ag
        is_our_home_at_home = (r.home_team_id == home_api)
        our_score = hg if is_our_home_at_home else ag
        their_score = ag if is_our_home_at_home else hg
        if our_score > their_score:
            home_wins += 1
        elif our_score < their_score:
            away_wins += 1
        else:
            draws += 1
        if last_str is None and r.fixture_date:
            last_str = (
                f"{r.home_team_name or '?'} {hg}-{ag} {r.away_team_name or '?'} "
                f"({r.fixture_date.date().isoformat()})"
            )

    return {
        "meetings": len(rows),
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "agg_goals_per_meeting": round(goals / len(rows), 2),
        "last": last_str,
    }


def _empty_h2h() -> dict:
    return {
        "meetings": 0,
        "home_wins": 0,
        "draws": 0,
        "away_wins": 0,
        "agg_goals_per_meeting": None,
        "last": None,
    }


def _absences(match_id: str, team_code: str) -> list[dict]:
    """Suspensions ledger — count only for now (the override file doesn't
    carry names yet; follow-up is to enrich it). Names will appear once we
    wire the football-data.org card-accumulation feed into a richer record.
    """
    count = get_suspension_count(match_id, team_code)
    if count <= 0:
        return []
    return [{
        "name": None,
        "reason": "suspended (card accumulation)",
        "count": count,
    }]


def _stakes(db: Session, match: Match) -> str:
    """One-sentence framing of what this match means for both sides.

    Heuristic for v1: matchday + group position. Knockout-round specifics
    (single-elimination stakes) are handled by the round name itself.
    """
    if not match.matchday:
        return f"Group {match.group} fixture."
    md = match.matchday
    if md == 1:
        return f"Matchday 1 — Group {match.group} opener. A win swings ~30 percentage points of qualification odds."
    if md == 2:
        return f"Matchday 2 — Group {match.group}. The losing side here typically needs a Matchday 3 win + favourable other-game results to advance."
    if md == 3:
        return "Matchday 3 — final group game. Both sides know the exact result they need."
    # Knockout matchdays (4+)
    return "Knockout fixture — single elimination."


def build_pre_match_context(match_id: str, db: Session) -> Optional[dict]:
    """Compose the full pre-match brief. Returns None when match_id not found.

    Caller is `/matches/{id}/pre-match-context`. Async model-swing-from-
    absences is layered on top by the route handler (this function stays
    synchronous so it's testable in isolation).
    """
    match = db.get(Match, match_id)
    if not match:
        return None

    home_code = match.home_code
    away_code = match.away_code
    home_api = TEAM_IDS.get(home_code)
    away_api = TEAM_IDS.get(away_code)

    home_scoring = _scoring_stats(db, home_code)
    away_scoring = _scoring_stats(db, away_code)
    home_archive = season_aggregates(home_api, db) if home_api else None
    away_archive = season_aggregates(away_api, db) if away_api else None

    def _merge_stats(scoring: dict, archive: Optional[dict]) -> dict:
        """Combine real-match scoring stats with archive-derived peripherals."""
        out = dict(scoring)
        if archive:
            out.update({
                "corners_per_match": archive.get("corners_per_match"),
                "yellow_per_match":  archive.get("yellow_per_match"),
                "shots_on_target_per_match": archive.get("shots_on_target_per_match"),
                "xg_per_match":      archive.get("xg_per_match"),
                "possession_avg":    archive.get("possession_avg"),
                "archive_matches_sampled": archive.get("matches_sampled"),
            })
        return out

    return {
        "match_id": match_id,
        "stakes": _stakes(db, match),
        "home_form": _recent_form(db, home_code),
        "away_form": _recent_form(db, away_code),
        "home_absences": _absences(match_id, home_code),
        "away_absences": _absences(match_id, away_code),
        "season_stats": {
            "home": _merge_stats(home_scoring, home_archive),
            "away": _merge_stats(away_scoring, away_archive),
        },
        "h2h_summary": _h2h_summary(db, home_code, away_code),
        # Layered on by the route handler — sync stub here.
        "model_swing_from_absences": None,
    }
