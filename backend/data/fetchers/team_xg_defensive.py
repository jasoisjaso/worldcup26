"""Defensive xG multiplier — pairs with team_xg.py.

team_xg.py reads each team's ATTACKING xG (the xg column in fixture_archive)
and nudges that team's own attacking lambda up/down. This file adds the
DEFENSIVE side: how much xG each team has CONCEDED per match, and uses that
to nudge their OPPONENT'S attacking lambda down (strong defence suppresses
you) or up (weak defence helps you).

Why this matters
----------------
Without a defensive signal, ELO is the only resilience input. ELO is a
goal-difference proxy, which conflates strong-attack-weak-defence sides with
the inverse. Real WC contenders differentiate on defence — France and Italy
have wildly different xG profiles at similar ELOs.

Data source
-----------
fixture_archive holds one row per (team, fixture). For "team T's xG conceded
in fixture F" we look up the OTHER team's xG row for the same api_fixture_id.
Self-join in one query, average over the last N archived fixtures.

Same caps + neutral defaults as team_xg.py so the pair compose predictably:
  - ±5% effect on lambda (matches attack side)
  - Reference 1.3 xGA/match (xGA = xG against)
  - Neutral 1.0 below the min-sample floor
"""
from __future__ import annotations

from sqlalchemy.orm import aliased

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.session import SessionLocal
from backend.db.models import FixtureArchive

_MIN_SAMPLE = 3
_REFERENCE_XGA = 1.3
_XGA_SCALE = 0.05
_XGA_SPREAD = 0.7


def _team_recent_xga(team_api_id: int, db, n: int = 6) -> tuple[float | None, int]:
    """Average xG CONCEDED over the last N archived fixtures.

    For each fixture team T played, find the OPPOSING team's xG entry on the
    same api_fixture_id — that's what T's defence allowed. Skip rows where
    either side's xg is null.
    """
    own = aliased(FixtureArchive)
    opp = aliased(FixtureArchive)
    rows = (
        db.query(opp.xg)
        .select_from(own)
        .join(
            opp,
            (opp.api_fixture_id == own.api_fixture_id) & (opp.team_api_id != own.team_api_id),
        )
        .filter(own.team_api_id == team_api_id)
        .filter(opp.xg.isnot(None))
        .order_by(own.captured_at.desc())
        .limit(n)
        .all()
    )
    vals = [r[0] for r in rows if r[0] is not None]
    if len(vals) < _MIN_SAMPLE:
        return None, len(vals)
    return sum(vals) / len(vals), len(vals)


def _xga_to_mult(avg_xga: float | None) -> float:
    """High xGA = weak defence = bumps OPPONENT's attack lambda UP (>1.0).
    Low xGA  = strong defence = damps OPPONENT's attack lambda DOWN (<1.0).
    """
    if avg_xga is None:
        return 1.0
    ratio = (avg_xga - _REFERENCE_XGA) / _XGA_SPREAD
    ratio = max(-1.0, min(1.0, ratio))
    return round(1.0 + _XGA_SCALE * ratio, 4)


def get_xg_defensive_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Return (home_lambda_mult, away_lambda_mult) keyed on the OPPOSING
    team's defensive resilience.

      home_lambda_mult comes from AWAY team's xGA → away's defence
        determines how much home is suppressed.
      away_lambda_mult comes from HOME team's xGA → home's defence
        determines how much away is suppressed.

    Synchronous + DB-only — no API calls. Defaults to (1.0, 1.0) for any
    team without enough archived fixtures.
    """
    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id and not away_id:
        return 1.0, 1.0

    db = SessionLocal()
    try:
        # AWAY team's xGA dictates HOME's lambda.
        away_xga = _team_recent_xga(away_id, db)[0] if away_id else None
        # HOME team's xGA dictates AWAY's lambda.
        home_xga = _team_recent_xga(home_id, db)[0] if home_id else None
    finally:
        db.close()

    return _xga_to_mult(away_xga), _xga_to_mult(home_xga)
