"""Tests for the model-uncertainty signal.

The engine already computes TWO independent views of a match: the ELO-derived
lambdas and the Dixon-Coles fitted lambdas. When they disagree strongly, that's
genuine model uncertainty — a free, no-dependency 'we're less sure here' flag
(no external ClubElo/Understat scrape needed; ClubElo is club-only and useless
for a World Cup, which is why we derive uncertainty internally instead).
"""
from __future__ import annotations

from backend.models.elo_model import lambda_divergence, uncertainty_flag


def test_no_divergence_when_views_agree():
    # ELO and DC produce the same total goal expectation → zero divergence.
    d = lambda_divergence((1.5, 1.0), (1.5, 1.0))
    assert d == 0.0


def test_divergence_grows_with_disagreement():
    small = lambda_divergence((1.5, 1.0), (1.6, 1.1))
    big = lambda_divergence((1.5, 1.0), (2.4, 0.4))
    assert big > small > 0.0


def test_uncertainty_flag_tiers():
    # Agreement → confident.
    assert uncertainty_flag((1.5, 1.0), (1.52, 0.98)) == "confident"
    # Mild disagreement → moderate.
    assert uncertainty_flag((1.5, 1.0), (1.9, 0.8)) == "moderate"
    # Strong disagreement → uncertain.
    assert uncertainty_flag((1.4, 1.1), (2.6, 0.3)) == "uncertain"


def test_uncertainty_flag_none_when_no_dc():
    # No DC view available (None) → no signal rather than a fake "confident".
    assert uncertainty_flag((1.5, 1.0), None) is None
