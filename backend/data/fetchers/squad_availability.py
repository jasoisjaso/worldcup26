"""Squad availability + continuity modifier from harvested data.

Two harvested signals, both DB-only (zero API cost), folded into one small
defensive/attacking lambda nudge:

  1. Sidelined key players (PlayerSidelined) — a team missing multiple players
     is weaker than its ELO implies.
  2. Squad continuity (FixtureLineup overlap between consecutive matches) — a
     heavily-rotated XI tends to underperform a settled one.

Like every other modifier here it is NEUTRAL (1.0) until the harvested tables
have enough data for a team, and capped tight (±4%) so it never disturbs the
well-calibrated ELO+DC core. ELO + form remain the primary signal.
"""
from __future__ import annotations

from backend.data.fetchers.injuries import TEAM_IDS
from backend.data import computed_metrics as _cm
from backend.db.session import SessionLocal
from backend.db.models import PlayerSidelined

# Max ±4% effect on a team's lambda.
_CAP = 0.04

# Each currently-sidelined player costs this much lambda, up to the cap.
_PER_SIDELINED = 0.012

# Continuity reference: a fully-settled XI (overlap 1.0) is neutral; every
# starter swapped from last match shaves a little attacking sharpness.
_CONTINUITY_REFERENCE = 0.8   # ~9/11 retained is "normal"
_CONTINUITY_SCALE = 0.05      # 1.0 spread in overlap → 5% (then capped)


def _count_sidelined(team_api_id: int, db) -> int:
    """Players currently flagged sidelined for this team (open-ended or future end)."""
    from datetime import datetime
    now = datetime.utcnow()
    rows = (
        db.query(PlayerSidelined)
        .filter(PlayerSidelined.team_api_id == team_api_id)
        .all()
    )
    active = 0
    for r in rows:
        end = getattr(r, "end_date", None)
        if end is None or end >= now:
            active += 1
    return active


def _team_availability_mult(team_api_id: int, db) -> float:
    """Combine sidelined count + squad continuity into one capped multiplier."""
    adj = 0.0

    sidelined = _count_sidelined(team_api_id, db)
    if sidelined:
        adj -= min(_CAP, sidelined * _PER_SIDELINED)

    continuity = _cm.squad_continuity(team_api_id, db)
    if continuity is not None:
        # Below the reference (lots of rotation) → small penalty; above → tiny bonus.
        cont_adj = (continuity - _CONTINUITY_REFERENCE) * _CONTINUITY_SCALE
        adj += max(-_CAP, min(_CAP, cont_adj))

    adj = max(-_CAP, min(_CAP, adj))
    return round(1.0 + adj, 4)


def get_squad_availability_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Return (home_mult, away_mult). DB-only, neutral when no data.

    Safe to call for every match — defaults to (1.0, 1.0) for any team without
    harvested sidelined/lineup rows.
    """
    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id and not away_id:
        return 1.0, 1.0

    db = SessionLocal()
    try:
        home_mult = _team_availability_mult(home_id, db) if home_id else 1.0
        away_mult = _team_availability_mult(away_id, db) if away_id else 1.0
    finally:
        db.close()

    return home_mult, away_mult
