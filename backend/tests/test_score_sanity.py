"""Sanity-check audit: stored Match scores vs MatchEvent goal totals.

The 2026-06-21 incident — Odds API matched a historical Haiti 1-0 Scotland
friendly and overwrote our WC row — must never silently happen again. This
test ensures the audit (a) catches a swap and auto-fixes it, (b) catches a
magnitude mismatch and logs an alert without auto-fixing (events could be
incomplete; we don't want to clobber a real result with a half-captured one).
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, Match, MatchEvent
from backend.data import score_sanity as ss
from backend.data.fetchers.injuries import TEAM_IDS


def _memdb():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _patch_session(monkeypatch, SessionFactory):
    monkeypatch.setattr(ss, "SessionLocal", SessionFactory)
    # Stub the HT backfill so the audit doesn't try to re-derive HT in tests.
    import backend.data.ht_score_backfill as ht
    monkeypatch.setattr(ht, "backfill_ht_scores_from_events", lambda: {"updated_from_events": 0})


def _add_goal(db, match_id: str, team_id: int, elapsed: int) -> None:
    db.add(MatchEvent(
        match_id=match_id, team_id=team_id, type="Goal",
        elapsed=elapsed, player_name="Test", detail="Normal Goal",
    ))


def test_swap_orientation_is_auto_fixed(monkeypatch):
    SessionFactory = _memdb()
    _patch_session(monkeypatch, SessionFactory)
    db = SessionFactory()
    # Pick two real WC team codes so the api_id lookup works.
    home_code, away_code = "ht", "gb-sct"
    home_api, away_api = TEAM_IDS[home_code], TEAM_IDS[away_code]
    # Match stored as ht 1-0 sct, but the actual goal is by Scotland.
    db.add(Match(
        id="M_swap", home_code=home_code, away_code=away_code,
        status="complete", home_score=1, away_score=0,
    ))
    _add_goal(db, "M_swap", away_api, 28)  # Scotland scored
    db.commit()
    db.close()

    result = ss.audit_match_scores()
    assert result["swap_fixed"] == 1
    assert result["mismatched"] == 0

    db = SessionFactory()
    m = db.get(Match, "M_swap")
    assert (m.home_score, m.away_score) == (0, 1)  # swapped to match events
    db.close()


def test_correct_orientation_is_left_alone(monkeypatch):
    SessionFactory = _memdb()
    _patch_session(monkeypatch, SessionFactory)
    db = SessionFactory()
    home_code, away_code = "ar", "br"
    home_api, away_api = TEAM_IDS[home_code], TEAM_IDS[away_code]
    db.add(Match(
        id="M_ok", home_code=home_code, away_code=away_code,
        status="complete", home_score=2, away_score=1,
    ))
    # Argentina 2, Brazil 1
    _add_goal(db, "M_ok", home_api, 10)
    _add_goal(db, "M_ok", home_api, 50)
    _add_goal(db, "M_ok", away_api, 70)
    db.commit()
    db.close()

    result = ss.audit_match_scores()
    assert result["ok"] == 1
    assert result["swap_fixed"] == 0
    assert result["mismatched"] == 0

    db = SessionFactory()
    m = db.get(Match, "M_ok")
    assert (m.home_score, m.away_score) == (2, 1)  # unchanged
    db.close()


def test_magnitude_mismatch_alerts_without_fixing(monkeypatch):
    """Stored 3-0 but events only captured 1-0 — DON'T auto-fix (events may
    be incomplete). Log an alert for operator review."""
    SessionFactory = _memdb()
    _patch_session(monkeypatch, SessionFactory)
    db = SessionFactory()
    home_code, away_code = "us", "py"
    home_api, _ = TEAM_IDS[home_code], TEAM_IDS[away_code]
    db.add(Match(
        id="M_mismatch", home_code=home_code, away_code=away_code,
        status="complete", home_score=3, away_score=0,
    ))
    # Only 1 goal event captured (live poller missed two)
    _add_goal(db, "M_mismatch", home_api, 10)
    db.commit()
    db.close()

    result = ss.audit_match_scores()
    assert result["mismatched"] == 1
    assert result["swap_fixed"] == 0
    assert len(result["alerts"]) == 1
    assert result["alerts"][0]["match_id"] == "M_mismatch"

    # Stored score must NOT have been overwritten — incomplete events can't
    # be trusted to authoritatively replace a possibly-correct stored score.
    db = SessionFactory()
    m = db.get(Match, "M_mismatch")
    assert (m.home_score, m.away_score) == (3, 0)
    db.close()


def test_no_events_is_skipped_cleanly(monkeypatch):
    """Pre-tournament matches we haven't yet polled live events for — skip
    silently, don't alert."""
    SessionFactory = _memdb()
    _patch_session(monkeypatch, SessionFactory)
    db = SessionFactory()
    db.add(Match(
        id="M_no_events", home_code="ar", away_code="br",
        status="complete", home_score=1, away_score=0,
    ))
    db.commit()
    db.close()

    result = ss.audit_match_scores()
    assert result["skipped_no_events"] == 1
    assert result["ok"] == 0
    assert result["mismatched"] == 0
