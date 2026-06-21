"""Rolling-xG attack form from our harvested fixture archive.

This is the FIRST modifier to read the harvested FixtureArchive table directly
(filled by the /fixtures/statistics harvest path). Where squad_xg.py infers
attacking strength from club-season top-scorer lists, this reads each national
team's ACTUAL recent xG output — the most direct attacking signal we have, and
it costs zero API calls because the data is already in our DB.

Design (matches the house style of the other lambda modifiers):
  - Neutral by default. Below a minimum sample of archived fixtures we return
    1.0 so we never inject noise for teams we haven't archived yet (most WC
    teams until their group games complete).
  - Small cap (±5%). ELO + form remain the primary signal; this is a secondary
    refinement, same philosophy as the h2h ±4% cap.
  - Centres on a league-typical 1.3 xG/match. A team averaging materially more
    gets a positive attack nudge, less gets a negative one.
"""
from __future__ import annotations

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.session import SessionLocal
from backend.db.models import FixtureArchive

# Minimum archived fixtures (with a real xg value) before we trust the signal.
_MIN_SAMPLE = 3

# Reference xG/match the multiplier centres on. A team at this level gets 1.0.
_REFERENCE_XG = 1.3

# Max ±5% effect on lambda.
_XG_SCALE = 0.05

# How far above/below reference counts as a "full" deviation (caps the ratio).
_XG_SPREAD = 0.7


def _team_recent_xg(team_api_id: int, db, n: int = 6) -> tuple[float | None, int]:
    """Average xG over the last N archived fixtures. Returns (avg, sample_size)."""
    rows = (
        db.query(FixtureArchive.xg)
        .filter(FixtureArchive.team_api_id == team_api_id)
        .filter(FixtureArchive.xg.isnot(None))
        .order_by(FixtureArchive.captured_at.desc())
        .limit(n)
        .all()
    )
    vals = [r[0] for r in rows if r[0] is not None]
    if len(vals) < _MIN_SAMPLE:
        return None, len(vals)
    return sum(vals) / len(vals), len(vals)


def _xg_to_mult(avg_xg: float | None) -> float:
    """Map an average xG/match onto a capped lambda multiplier centred on 1.0."""
    if avg_xg is None:
        return 1.0
    ratio = (avg_xg - _REFERENCE_XG) / _XG_SPREAD
    ratio = max(-1.0, min(1.0, ratio))
    return round(1.0 + _XG_SCALE * ratio, 4)


def get_xg_form_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Return (home_mult, away_mult) from each team's rolling archived xG.

    Synchronous + DB-only — no API calls. Defaults to (1.0, 1.0) for any team
    without enough archived fixtures, so it is safe to call for every match
    from kickoff one of the tournament.
    """
    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id and not away_id:
        return 1.0, 1.0

    db = SessionLocal()
    try:
        home_xg = _team_recent_xg(home_id, db)[0] if home_id else None
        away_xg = _team_recent_xg(away_id, db)[0] if away_id else None
    finally:
        db.close()

    return _xg_to_mult(home_xg), _xg_to_mult(away_xg)
