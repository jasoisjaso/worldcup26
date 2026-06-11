"""
Match-specific lambda modifiers for WC2026 group stage.

Three independent effects applied after base DC/ELO lambdas:
  1. altitude_lambda_bonus     - both teams score more at high-altitude venues
  2. rest_days_multipliers     - relative rest gap since last WC game
  3. dead_rubber_multipliers   - squads rotating starters in settled MD3 games

md1_rho() adjusts Dixon-Coles rho for MD1 conservatism (more draws in openers).
"""
from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session

# High-altitude venues (metres above sea level from venue_advantage.py)
# Research consensus: ~0.10-0.15 additional expected goals per team at 2240m
# Both teams score more — reduced air resistance, ball pace, keeper/defender fatigue
_VENUE_ALTITUDE_BONUS: dict[str, float] = {
    "mexico city": 0.12,   # 2240m — Estadio Azteca
    "guadalajara": 0.06,   # 1522m — Estadio Akron
    # Monterrey 538m: below threshold, no adjustment
}

# Rest days: each day of advantage over opponent = +2% lambda, capped at ±6%
_REST_PER_DAY = 0.02
_REST_CAP = 0.06

# Confirmed dead-rubber reduction — teams rest starters when qualification settled
_DEAD_RUBBER_FACTOR = 0.87

# MD1 conservative play: teams enter tournament openers defensively
# Less-negative rho = less low-score correction = closer to Poisson = slightly more draws
MD1_RHO = -0.05
DEFAULT_RHO = -0.13


def md1_rho(matchday: int | None) -> float:
    """Return the DC rho to use — relaxed for MD1 to inflate draw probability."""
    return MD1_RHO if matchday == 1 else DEFAULT_RHO


def _city_key(venue: str) -> str:
    parts = venue.lower().split(",")
    return parts[-1].strip() if parts else ""


def altitude_lambda_bonus(venue: str) -> float:
    """
    Additive expected-goals bonus applied to BOTH teams at high-altitude venues.
    Called from group_predictor before form modifier.
    """
    return _VENUE_ALTITUDE_BONUS.get(_city_key(venue), 0.0)


def rest_days_multipliers(
    home_code: str,
    away_code: str,
    match_kickoff: datetime,
    db: Session,
) -> tuple[float, float]:
    """
    Return (home_mult, away_mult) based on relative rest since last WC game.
    A team with 3 more days rest than their opponent gets a +6% lambda boost.
    First match of tournament (no previous game) → 1.0 for both.
    """
    from backend.db.models import Match as DBMatch

    completed = (
        db.query(DBMatch)
        .filter(DBMatch.status == "complete", DBMatch.kickoff.isnot(None))
        .all()
    )

    match_date = match_kickoff.date() if isinstance(match_kickoff, datetime) else match_kickoff

    def last_wc_date(code: str):
        dates = [
            m.kickoff.date()
            for m in completed
            if (m.home_code == code or m.away_code == code) and m.kickoff
        ]
        return max(dates) if dates else None

    home_last = last_wc_date(home_code)
    away_last = last_wc_date(away_code)

    if home_last is None and away_last is None:
        return 1.0, 1.0

    home_days = (match_date - home_last).days if home_last else 0
    away_days = (match_date - away_last).days if away_last else 0
    diff = home_days - away_days

    home_mult = 1.0 + max(-_REST_CAP, min(_REST_CAP, diff * _REST_PER_DAY))
    away_mult = 1.0 + max(-_REST_CAP, min(_REST_CAP, -diff * _REST_PER_DAY))
    return home_mult, away_mult


def dead_rubber_multipliers(
    home_code: str,
    away_code: str,
    matchday: int,
    group: str,
    db: Session,
) -> tuple[float, float]:
    """
    Return (home_factor, away_factor). Applies _DEAD_RUBBER_FACTOR (0.87) if the
    team already has qualification or elimination confirmed before MD3 kicks off.

    Qualified: 6 points (won both MD1+MD2 games) — guaranteed top-2 in a group of 4.
    Eliminated: 0 points + 2 other group teams already on 6 pts (both spots taken).
    """
    if matchday != 3:
        return 1.0, 1.0

    from backend.db.models import Match as DBMatch

    completed = [
        m for m in db.query(DBMatch).filter(
            DBMatch.status == "complete",
            DBMatch.group == group,
            DBMatch.matchday < 3,
        ).all()
        if m.home_score is not None and m.away_score is not None
    ]

    points: dict[str, int] = {}
    group_teams: set[str] = set()
    for m in completed:
        group_teams.add(m.home_code)
        group_teams.add(m.away_code)
        hs, as_ = m.home_score, m.away_score
        points[m.home_code] = points.get(m.home_code, 0) + (3 if hs > as_ else (1 if hs == as_ else 0))
        points[m.away_code] = points.get(m.away_code, 0) + (3 if as_ > hs else (1 if hs == as_ else 0))

    def _is_dead_rubber(code: str) -> bool:
        my_pts = points.get(code, 0)
        if my_pts >= 6:
            return True
        others = [points.get(t, 0) for t in group_teams if t != code]
        if my_pts == 0 and sum(1 for p in others if p >= 6) >= 2:
            return True
        return False

    return (
        _DEAD_RUBBER_FACTOR if _is_dead_rubber(home_code) else 1.0,
        _DEAD_RUBBER_FACTOR if _is_dead_rubber(away_code) else 1.0,
    )
