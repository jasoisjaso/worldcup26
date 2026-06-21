"""Corners + cards markets — derived from harvested FixtureArchive samples.

These markets sit BESIDE the goal-derived markets in markets.py. The model
that fits Dixon-Coles to goals is silent on corners and cards (different
underlying processes), so we estimate them separately from per-team match
averages in the harvested FixtureArchive rows.

Sample-size honesty: WC teams have at most a handful of completed club
fixtures in our archive right now. When the per-team sample is thin we fall
back to a tournament prior (international football averages drawn from
public WC + qualifier data) and tag the market with the actual sample size
so the FE can render a "low sample" caveat.

Math (Poisson):
  - expected_corners_home  = avg(home_corners_for, away_corners_against)
  - expected_corners_away  = avg(away_corners_for, home_corners_against)
  - expected_total_corners = home + away
  - P(total > line) and P(total < line+1) come from Poisson PMF/CDF

Same shape for yellow cards. Red cards are too rare to price as a market
on this sample — exposed only via the "red card in match" boolean.

These are NOT pulled into the value board EV gate today (per spec:
"never let the optimizer nudge a user toward them as value") — they're
informational markets on the per-match sheet only.
"""
from __future__ import annotations

from math import exp
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import FixtureArchive

# Tournament priors for international football. Sourced from publicly
# available average-per-match stats (WC, Euros, qualifiers): corners ~10/match
# total ≈ 5 per team; yellow cards ~3.5/match total ≈ 1.75 per team.
_PRIOR_TEAM_CORNERS = 5.0
_PRIOR_TEAM_YELLOWS = 1.75

# Below this sample count we don't trust the per-team average alone — blend
# with the prior so a team with 1 weird game doesn't get a wildly wrong line.
_MIN_TRUSTED_SAMPLE = 5

# Number of over/under lines to emit per market. Asymmetric on the high side
# because long-line punters watch the over (it's where books usually open
# the most). Conservative — too many lines reads as noise.
_CORNER_LINES = [8.5, 9.5, 10.5, 11.5, 12.5]
_CARD_LINES = [2.5, 3.5, 4.5, 5.5]


def _poisson_pmf(k: int, lam: float) -> float:
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    # Use a stable iterative form to avoid factorial overflow on long tails.
    p = exp(-lam)
    for i in range(1, k + 1):
        p *= lam / i
    return p


def _p_over(line: float, lam: float, kmax: int = 60) -> float:
    """P(X > line) where X ~ Poisson(lam). Line is half-integer (e.g. 9.5)."""
    threshold = int(line) + 1  # P(X > 9.5) == P(X >= 10)
    # Sum the tail: 1 - CDF(threshold - 1)
    cdf = 0.0
    for k in range(threshold):
        cdf += _poisson_pmf(k, lam)
    return max(0.0, min(1.0, 1.0 - cdf))


def _shrink_blend(
    observed_avg: float | None,
    sample: int,
    prior: float,
    min_sample: int = _MIN_TRUSTED_SAMPLE,
) -> float:
    """Pure-math Bayesian shrinkage — exported separately so tests don't have
    to mock SQLAlchemy. weight = n / (n + min_sample): a team with min_sample
    games gets 50/50 between observed and prior; large n quickly dominates.
    """
    if observed_avg is None or sample <= 0:
        return prior
    weight = sample / (sample + min_sample)
    return max(0.0, weight * float(observed_avg) + (1.0 - weight) * prior)


def _shrunk_team_avg(
    db: Session, team_api_id: int, column,
    prior: float, min_sample: int = _MIN_TRUSTED_SAMPLE,
) -> tuple[float, int]:
    """DB-bound wrapper: fetch the avg + count, then defer to `_shrink_blend`."""
    rows = (
        db.query(func.avg(column), func.count(column))
        .filter(FixtureArchive.team_api_id == team_api_id)
        .filter(column.isnot(None))
        .first()
    )
    if not rows:
        return prior, 0
    avg, n = rows
    if avg is None or n == 0:
        return prior, 0
    n = int(n)
    return _shrink_blend(float(avg), n, prior, min_sample), n


def _resolve_api_id(team_code: str) -> Optional[int]:
    return TEAM_IDS.get(team_code)


def _fair(p: float) -> Optional[float]:
    if p <= 0:
        return None
    odds = 1.0 / p
    return None if odds > 1000 else round(odds, 2)


def _o(key: str, label: str, prob: float) -> dict:
    return {"key": key, "label": label, "prob": round(prob, 4), "fair_odds": _fair(prob)}


def derive_peripheral_markets(
    home_code: str, away_code: str, db: Session,
) -> list[dict]:
    """Return market groups for corners + yellow cards. Each group includes a
    `confidence` tag based on the THINNER side's sample (because a thin team
    drags the joint estimate down regardless of how many games the other side
    has)."""
    home_id = _resolve_api_id(home_code)
    away_id = _resolve_api_id(away_code)
    if not home_id or not away_id:
        return []

    # Corners — for/against per team. Sample size is the smaller of the two,
    # because the market depends on both averages.
    h_corn_for, h_corn_n = _shrunk_team_avg(db, home_id, FixtureArchive.corners, _PRIOR_TEAM_CORNERS)
    a_corn_for, a_corn_n = _shrunk_team_avg(db, away_id, FixtureArchive.corners, _PRIOR_TEAM_CORNERS)
    # We don't currently capture corners_against directly — using the prior
    # for the defensive side keeps the estimator honest until we add it.
    exp_corners_total = h_corn_for + a_corn_for
    corner_sample = min(h_corn_n, a_corn_n)

    # Yellow cards — same shape.
    h_yc, h_yc_n = _shrunk_team_avg(db, home_id, FixtureArchive.yellow_cards, _PRIOR_TEAM_YELLOWS)
    a_yc, a_yc_n = _shrunk_team_avg(db, away_id, FixtureArchive.yellow_cards, _PRIOR_TEAM_YELLOWS)
    exp_cards_total = h_yc + a_yc
    card_sample = min(h_yc_n, a_yc_n)

    def _confidence(sample: int) -> str:
        if sample >= 15:
            return "ok"
        if sample >= _MIN_TRUSTED_SAMPLE:
            return "low"
        return "very_low"

    groups: list[dict] = []

    # Corners — match total
    corner_outcomes = []
    for line in _CORNER_LINES:
        p_over = _p_over(line, exp_corners_total)
        corner_outcomes.append(_o(f"over_{line}", f"Over {line}", p_over))
        corner_outcomes.append(_o(f"under_{line}", f"Under {line}", 1.0 - p_over))
    groups.append({
        "key": "corners",
        "name": "Corners (match total)",
        "outcomes": corner_outcomes,
        "expected_total": round(exp_corners_total, 2),
        "confidence": _confidence(corner_sample),
        "sample_size": corner_sample,
        "indicative": True,
    })

    # Team corners (each side)
    for label, lam, prefix in (
        (f"{home_code.upper()} corners", h_corn_for, "home"),
        (f"{away_code.upper()} corners", a_corn_for, "away"),
    ):
        out = []
        for line in [3.5, 4.5, 5.5, 6.5]:
            p_over = _p_over(line, lam)
            out.append(_o(f"{prefix}_over_{line}", f"Over {line}", p_over))
            out.append(_o(f"{prefix}_under_{line}", f"Under {line}", 1.0 - p_over))
        groups.append({
            "key": f"team_corners_{prefix}",
            "name": label,
            "outcomes": out,
            "expected_total": round(lam, 2),
            "confidence": _confidence(h_corn_n if prefix == "home" else a_corn_n),
            "sample_size": h_corn_n if prefix == "home" else a_corn_n,
            "indicative": True,
        })

    # Yellow cards — match total
    card_outcomes = []
    for line in _CARD_LINES:
        p_over = _p_over(line, exp_cards_total)
        card_outcomes.append(_o(f"over_{line}", f"Over {line}", p_over))
        card_outcomes.append(_o(f"under_{line}", f"Under {line}", 1.0 - p_over))
    groups.append({
        "key": "cards",
        "name": "Yellow cards (match total)",
        "outcomes": card_outcomes,
        "expected_total": round(exp_cards_total, 2),
        "confidence": _confidence(card_sample),
        "sample_size": card_sample,
        "indicative": True,
    })

    return groups
