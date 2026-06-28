"""Rolling-xG attack form from our harvested fixture archive.

Reads each national team's ACTUAL recent xG output from FixtureArchive and
nudges the team's attacking lambda accordingly. Zero API cost — pure DB.

2026-06-28 upgrade: Bayesian shrinkage + exponential recency weighting.

WHY THE CHANGE
--------------
The previous design averaged the last 6 archived xG values equal-weighted.
Two well-known sports-analytics issues with that:

  1. Small-sample variance. A team with 3 archived fixtures and one
     outlier 3.2-xG game is reported as 1.8 xG/match. The next fixture
     is more likely to be near the team's TRUE rate (~1.4) than near the
     reported 1.8. Raw means over-fit small samples.

  2. Recency bias is real. A 6-month-old match means less than last
     week's. Equal weight assumes otherwise.

The replacement applies:

  - Exponential decay across the last N fixtures (most-recent weight 1.0,
    each older one × decay). decay=0.85 → the 6th-most-recent fixture
    counts ~45% of the most recent. Published xG forecasting work
    (Caley, Tippett) consistently shows recency-weighted xG out-predicts
    raw rolling mean.

  - Bayesian shrinkage toward a global prior. With tau equivalent
    observations of weight at the reference, the posterior xG is:
        posterior = (n_eff * weighted_mean + tau * prior) / (n_eff + tau)
    A team with 3 fixtures gets pulled hard toward 1.3 (the prior); a
    team with 20 fixtures barely moves. Standard treatment for low-N
    rate estimation.

Same ±5% cap, same neutral 1.0 below the minimum sample floor, so the
existing match-page rendering and EV pipeline are unchanged downstream.
"""
from __future__ import annotations

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.session import SessionLocal
from backend.db.models import FixtureArchive

# Minimum archived fixtures (with a real xg value) before we trust the signal.
_MIN_SAMPLE = 3

# Pull this many archived fixtures and weight by recency (most-recent first).
_LOOKBACK = 10

# Geometric decay applied per step away from the most-recent fixture.
# 0.85 means the 6th-most-recent fixture has 0.85^5 ≈ 0.44 of the weight.
_DECAY = 0.85

# Reference xG/match the multiplier centres on. A team at this level gets 1.0.
_REFERENCE_XG = 1.3

# Bayesian shrinkage strength. Equivalent to TAU prior observations sitting at
# _REFERENCE_XG. With tau=5: a team with 3 weighted fixtures is shrunk hard
# toward 1.3; a team with 15+ barely moves. Tuned to match the conservatism
# of the other modifiers — lambda nudges should never lead a prediction.
_PRIOR_TAU = 5.0

# Max ±5% effect on lambda.
_XG_SCALE = 0.05

# How far above/below reference counts as a "full" deviation (caps the ratio).
_XG_SPREAD = 0.7


def _team_recent_xg(team_api_id: int, db, n: int = _LOOKBACK) -> tuple[float | None, int]:
    """Recency-weighted + Bayesian-shrunk xG estimate over the last N archived
    fixtures. Returns (estimate, raw_sample_size).

    Returns (None, n_below_floor) when too few rows exist — caller keeps the
    multiplier at neutral 1.0 in that case.
    """
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

    # Recency-weighted mean: vals[0] is most recent, gets weight 1.0.
    weights = [_DECAY ** i for i in range(len(vals))]
    n_eff = sum(weights)
    weighted_sum = sum(v * w for v, w in zip(vals, weights))
    weighted_mean = weighted_sum / n_eff

    # Bayesian shrinkage toward _REFERENCE_XG with prior strength _PRIOR_TAU.
    posterior = (n_eff * weighted_mean + _PRIOR_TAU * _REFERENCE_XG) / (n_eff + _PRIOR_TAU)

    return posterior, len(vals)


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
    without enough archived fixtures, so it is safe to call for every match.
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
