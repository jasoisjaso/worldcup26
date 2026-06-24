"""Anytime goalscorer market — derives per-player scoring probability from
squad position + recent goal counts, scaled by the team's expected goals.

Design honesty:
  - Per-player /fixtures/players data is NOT yet harvested (0 PlayerHistory
    rows). That endpoint is the only source of goals_per_90 we'd actually
    trust. Until it's filled, this module falls back to a position-based
    prior derived from public international-football scoring rates.

  - PlayerTournamentStats DOES contain goal counts but is currently buggy
    (re-processing overwrites minutes with 0 — separate fix tracked).
    We treat any non-zero goal count as a positive signal that mildly
    boosts the position prior, but never as the primary number.

  - Output is always tagged `indicative: true` + a confidence label. Per
    project spec these are NOT pooled into the value-board EV gate.

Math:
  team_lambda             = model's expected goals for this team this match
  team_expected_goals_avg = team's prior average goals per match (≈ 1.2 intl)
  position_share          = position-based fraction of team goals this
                            player tends to take (striker 0.30, AM 0.13,
                            CM 0.07, DEF 0.03, GK 0.001)
  recency_boost           = 1.0 + 0.15 * recent_goals (capped at 1.8) when
                            player has any tournament goal logged. Adds
                            ~weight to known scorers without trusting the
                            buggy minutes data.
  expected_player_goals   = team_lambda * position_share * recency_boost
  P(scores ≥ 1)           = 1 - exp(-expected_player_goals)
"""
from __future__ import annotations

from math import exp
from typing import Optional

from sqlalchemy.orm import Session

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import PlayerProfile, PlayerTournamentStats

# Position-based share of team goals, derived from public WC/Euro qualifier
# data 2010-2022. Strikers take ~30% of team scoring, attacking mids ~13%,
# central mids 7%, fullbacks 4%, centre-backs 2%, GK negligible.
_POSITION_SHARE = {
    "attacker": 0.30,
    "midfielder": 0.10,
    "defender": 0.03,
    "goalkeeper": 0.001,
}

# Tournament-level average team goals per match for international football.
# Used to normalise team_lambda toward an expected-share baseline. Higher
# scoring teams pull the per-player number up; defensive teams pull it down.
_TEAM_BASELINE_GOALS = 1.30

# Cap on the recency_boost so a single hot tournament doesn't push a player's
# anytime-goal probability into nonsensically certain territory.
_RECENCY_CAP = 1.8
_RECENCY_PER_GOAL = 0.15

# Number of players per team to expose in the market — top N by expected
# scoring contribution. Books typically list 8-15; 8 keeps the FE readable.
_MAX_PLAYERS_PER_TEAM = 8


def _resolve_api_id(team_code: str) -> Optional[int]:
    return TEAM_IDS.get(team_code)


def _fair(p: float) -> Optional[float]:
    if p <= 0:
        return None
    odds = 1.0 / p
    return None if odds > 1000 else round(odds, 2)


def _position_share(position: Optional[str]) -> float:
    if not position:
        return _POSITION_SHARE["midfielder"]  # safe middle prior
    key = position.strip().lower()
    return _POSITION_SHARE.get(key, _POSITION_SHARE["midfielder"])


def _expected_player_goals(
    team_lambda: float, position: Optional[str], recent_goals: int,
) -> float:
    """Per-player expected goals for this match. See module docstring."""
    share = _position_share(position)
    boost = min(_RECENCY_CAP, 1.0 + _RECENCY_PER_GOAL * max(0, recent_goals))
    # Normalise team_lambda against the baseline so a team expected to score
    # double its prior gives every player double the chance, scaled by share.
    norm = team_lambda / _TEAM_BASELINE_GOALS if _TEAM_BASELINE_GOALS > 0 else 1.0
    return max(0.0, share * norm * boost * _TEAM_BASELINE_GOALS)


def _p_score(expected_goals: float) -> float:
    """P(scores ≥ 1) under Poisson(λ=expected_goals)."""
    return 1.0 - exp(-max(0.0, expected_goals))


def _team_players_with_goals(
    db: Session, team_api_id: int,
) -> list[tuple[PlayerProfile, int]]:
    """Return (profile, recent_goals) for every known player of the team.

    PlayerTournamentStats provides the goal count when available. We DO NOT
    trust the minutes column right now (data bug — separate fix) so we use
    goals alone as a soft signal.
    """
    profiles = (
        db.query(PlayerProfile)
        .filter(PlayerProfile.team_id == team_api_id)
        .all()
    )
    if not profiles:
        return []

    # One query to map player_id → recent_goals
    stat_rows = (
        db.query(PlayerTournamentStats.player_id, PlayerTournamentStats.goals)
        .filter(PlayerTournamentStats.team_id == team_api_id)
        .all()
    )
    goals_by_id = {row[0]: int(row[1] or 0) for row in stat_rows}

    return [(p, goals_by_id.get(p.player_id, 0)) for p in profiles]


def _team_anytime_goalscorers(
    db: Session, team_code: str, team_lambda: float, side: str,
) -> Optional[dict]:
    """Build one market group: the top N most likely scorers for this team.

    `side` is 'home' or 'away' — used to disambiguate keys when both teams'
    groups land in the same sheet.

    Returns None when we have no squad data for this team (skip the group
    rather than show an empty card).
    """
    api_id = _resolve_api_id(team_code)
    if not api_id:
        return None

    candidates = _team_players_with_goals(db, api_id)
    if not candidates:
        return None

    ranked = []
    for profile, recent_goals in candidates:
        # Skip GKs from the market list entirely — books don't price them as
        # anytime scorers because the probability is near-zero and pollutes
        # the top-N filter.
        if (profile.position or "").strip().lower() == "goalkeeper":
            continue
        exp_g = _expected_player_goals(team_lambda, profile.position, recent_goals)
        p_score = _p_score(exp_g)
        if p_score < 0.005:
            continue  # below display threshold — keeps the list useful
        ranked.append({
            "player_id": profile.player_id,
            "player_name": profile.name,
            "position": profile.position,
            "recent_goals": recent_goals,
            "expected_goals": round(exp_g, 3),
            "prob": round(p_score, 4),
        })

    if not ranked:
        return None

    ranked.sort(key=lambda r: r["prob"], reverse=True)
    ranked = ranked[:_MAX_PLAYERS_PER_TEAM]

    # Confidence: ok when we have any non-zero goal counts; otherwise we're
    # leaning entirely on position priors which is "very_low".
    any_goals = any(r["recent_goals"] > 0 for r in ranked)
    confidence = "low" if any_goals else "very_low"

    outcomes = [
        {
            "key": f"{side}_player_{r['player_id']}",
            "label": f"{r['player_name']} ({r['position'] or '?'})",
            "prob": r["prob"],
            "fair_odds": _fair(r["prob"]),
        }
        for r in ranked
    ]

    return {
        "key": f"anytime_goalscorer_{side}",
        "name": f"{team_code.upper()} anytime goalscorer",
        "outcomes": outcomes,
        "indicative": True,
        "confidence": confidence,
        "sample_size": sum(1 for r in ranked if r["recent_goals"] > 0),
        "expected_total": round(sum(r["expected_goals"] for r in ranked), 2),
    }


def derive_goalscorer_markets(
    home_code: str, away_code: str,
    lambda_home: float, lambda_away: float,
    db: Session,
) -> list[dict]:
    """Return up to two market groups: one per team's anytime scorers."""
    groups: list[dict] = []
    for code, lam, side in (
        (home_code, lambda_home, "home"),
        (away_code, lambda_away, "away"),
    ):
        group = _team_anytime_goalscorers(db, code, lam, side)
        if group:
            groups.append(group)
    return groups
