"""Smoke + shape tests for build_pre_match_context.

We don't try to stand up a populated DB here — the production live test
verifies the full payload against M001. These tests exercise the pure
helpers (h2h aggregation, stakes string, scoring math) so a logic bug
is caught locally before deploy.
"""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from backend.data import match_context as mc


class _FakeMatch:
    def __init__(self, group="C", matchday=3, status="complete",
                 home_code="ba", away_code="qa",
                 home_score=2, away_score=0,
                 kickoff=None):
        self.id = "M0_test"
        self.group = group
        self.matchday = matchday
        self.status = status
        self.home_code = home_code
        self.away_code = away_code
        self.home_score = home_score
        self.away_score = away_score
        self.kickoff = kickoff or datetime(2026, 6, 20, 19, 0)
        self.home_ht_score = None
        self.away_ht_score = None


def test_stakes_matchday_1():
    out = mc._stakes(db=None, match=_FakeMatch(matchday=1, group="C"))  # type: ignore[arg-type]
    assert "Matchday 1" in out
    assert "Group C" in out


def test_stakes_matchday_3():
    out = mc._stakes(db=None, match=_FakeMatch(matchday=3, group="C"))  # type: ignore[arg-type]
    assert "Matchday 3" in out
    assert "final group game" in out


def test_stakes_knockout():
    out = mc._stakes(db=None, match=_FakeMatch(matchday=4, group=None))  # type: ignore[arg-type]
    assert "Knockout" in out


def test_empty_h2h_shape():
    """When we have no H2H rows, return all-zero shape so the FE renders gracefully."""
    out = mc._empty_h2h()
    assert out["meetings"] == 0
    assert out["home_wins"] == 0
    assert out["draws"] == 0
    assert out["away_wins"] == 0
    assert out["last"] is None


def test_scoring_stats_no_matches():
    """No completed matches → None values, not NaN/exception."""
    class _FakeQuery:
        def filter(self, *a, **k): return self
        def order_by(self, *a): return self
        def limit(self, *a): return self
        def all(self): return []
    class _FakeDb:
        def query(self, *a): return _FakeQuery()
    out = mc._scoring_stats(_FakeDb(), "ba")  # type: ignore[arg-type]
    assert out["matches_sampled"] == 0
    assert out["goals_per_match"] is None
    assert out["btts_pct"] is None


def test_scoring_stats_simple_aggregation():
    """Two played matches: 2-0 W (home) and 1-2 L (away). Sanity check the totals."""
    m1 = _FakeMatch(home_code="ba", away_code="qa", home_score=2, away_score=0)
    m2 = _FakeMatch(home_code="ba", away_code="kr", home_score=1, away_score=2)
    class _FakeQuery:
        def filter(self, *a, **k): return self
        def order_by(self, *a): return self
        def limit(self, *a): return self
        def all(self): return [m1, m2]
    class _FakeDb:
        def query(self, *a): return _FakeQuery()
    out = mc._scoring_stats(_FakeDb(), "ba")  # type: ignore[arg-type]
    assert out["matches_sampled"] == 2
    # Goals for ba: 2 (in m1, home) + 1 (in m2, home) = 3 over 2 matches
    assert out["goals_per_match"] == 1.5
    # Goals against ba: 0 + 2 = 2 over 2
    assert out["conceded_per_match"] == 1.0
    # BTTS: m1 false (0-0 away), m2 true → 50%
    assert out["btts_pct"] == 0.5
    # Clean sheet: m1 yes (qa scored 0), m2 no → 50%
    assert out["cs_pct"] == 0.5


def test_absences_zero_returns_empty_list():
    """No suspensions = empty list (not a placeholder row)."""
    out = mc._absences("M_nonexistent", "ba")
    assert out == []
