"""Aggregate FixtureArchive rows into per-team season averages.

Read-only: no API calls. One SQL pass per team — cheap enough to call on
every `/matches/{id}/pre-match-context` request without caching.

Returns None when a team has zero archived fixtures so callers can decide
whether to fall back to a tournament prior or hide the section. Every
average row carries `matches_sampled` so the FE can render a sample-size
caveat — same honesty rule as the peripheral markets.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import FixtureArchive


def season_aggregates(team_api_id: int, db: Session, limit: int = 38) -> Optional[dict]:
    """Per-team averages across the most recent `limit` archived fixtures."""
    rows = (
        db.query(FixtureArchive)
        .filter(FixtureArchive.team_api_id == team_api_id)
        .order_by(FixtureArchive.captured_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None
    n = len(rows)

    # Sum-only-not-null helpers so a team with possession recorded in some
    # matches but not others doesn't average toward zero. xG is most often
    # null so we count separately for that one.
    def _avg(attr, default: float = 0):
        vals = [getattr(r, attr) for r in rows if getattr(r, attr) is not None]
        return round(sum(vals) / len(vals), 2) if vals else default

    return {
        "matches_sampled": n,
        "corners_per_match":         _avg("corners"),
        "yellow_per_match":          _avg("yellow_cards"),
        "red_per_match":             _avg("red_cards"),
        "shots_per_match":           _avg("shots_total"),
        "shots_on_target_per_match": _avg("shots_on_target"),
        "xg_per_match":              _avg("xg"),
        "possession_avg":            _avg("possession", default=50.0),
        "pass_accuracy_avg":         _avg("pass_accuracy"),
    }
