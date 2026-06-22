"""Locks down the match-interruption taxonomy added 2026-06-23 after FRA-IRQ.

Before this batch, a weather suspension (api-football status=INT/SUSP) caused
the stale-row sweep to silently mark the Match complete with the partial
score. These tests pin the new behaviour: interruption_status carries the
why, Match.status only becomes 'complete' on a REAL final whistle, and
calibration / FD-org both refuse to write off a partial result.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.models import Base, Match, LiveMatchState


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _make_match(db, mid="M042", status="upcoming", **kw):
    m = Match(
        id=mid,
        home_code="fr",
        away_code="iq",
        kickoff=datetime(2026, 6, 22, 21, 0, 0),
        status=status,
        **kw,
    )
    db.add(m)
    lms = LiveMatchState(
        match_id=mid,
        fixture_id_external=1539017,
        status="2H",
        elapsed_min=45,
        home_score=1,
        away_score=0,
        updated_at=datetime(2026, 6, 22, 22, 0, 0),
    )
    db.add(lms)
    db.commit()
    return m, lms


# ---------------------------------------------------------------------------
# _apply_interruption — the core lifecycle helper
# ---------------------------------------------------------------------------


def test_suspended_match_stays_upcoming_with_partial_score(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "SUSP", 1, 0, reason="weather")
    # Critical invariant — partial score MUST NOT be written to FT columns.
    assert m.home_score is None
    assert m.away_score is None
    assert m.partial_home_score == 1
    assert m.partial_away_score == 0
    assert m.interruption_status == "delayed"
    assert m.interruption_reason == "weather"
    assert m.interruption_started_at is not None
    # Match.status preserved — picks gate on != 'complete', delays don't flip it.
    assert m.status == "upcoming"
    # Live row reflects the real api status so the operator sees the truth.
    assert lms.status == "SUSP"


def test_int_treated_same_as_susp(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "INT", 1, 0, reason="weather")
    assert m.interruption_status == "delayed"
    assert m.home_score is None  # FRA-IRQ exact scenario


def test_postponed_match_flips_status(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "PST", None, None, reason="weather forecast")
    assert m.interruption_status == "postponed"
    assert m.status == "postponed"
    assert m.home_score is None
    assert m.away_score is None


def test_abandoned_match_flips_status_and_keeps_partial(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "ABD", 1, 0, reason="abandoned 45'")
    assert m.interruption_status == "abandoned"
    assert m.status == "abandoned"
    # FT columns stay NULL (calibration & standings consumers filter on
    # status=='complete', so an abandoned row vanishes from both).
    assert m.home_score is None
    assert m.away_score is None
    assert m.partial_home_score == 1
    assert m.partial_away_score == 0


def test_awarded_match_marks_complete_with_official_score(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    # Serbia-Albania style: governing body awards 3-0.
    _apply_interruption(db, m, lms, "AWD", 3, 0, reason="UEFA awarded 3-0")
    assert m.interruption_status == "awarded"
    assert m.status == "complete"
    assert m.home_score == 3
    assert m.away_score == 0
    # Picks remain void per industry rules — the void gate lives in the
    # settlement helpers, not the lifecycle helper.


def test_unknown_status_is_a_noop(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "XYZ", 1, 0, reason="ghost")
    assert m.interruption_status is None
    assert m.status == "upcoming"


def test_interruption_started_at_is_stamped_only_on_first_entry(db):
    from backend.data.fetchers.live import _apply_interruption
    m, lms = _make_match(db)
    _apply_interruption(db, m, lms, "SUSP", 1, 0, reason="weather")
    first = m.interruption_started_at
    assert first is not None
    # Re-applying the same interruption (a subsequent verify pass) must not
    # bump the timestamp, otherwise the watchdog's age-out never triggers.
    _apply_interruption(db, m, lms, "SUSP", 1, 0, reason="weather still")
    assert m.interruption_started_at == first


# ---------------------------------------------------------------------------
# Calibration logger — refuses to enrol interrupted matches
# ---------------------------------------------------------------------------


def test_calibration_gate_skips_interrupted_complete_rows(db, monkeypatch):
    from backend.data import calibration_logger
    from backend.db.models import PredictionSnapshot, ModelCalibrationLog

    # Awarded match has Match.status='complete' BUT picks must void AND
    # calibration must NOT score against an unearned scoreline.
    m, lms = _make_match(db, mid="M999", status="complete")
    m.home_score = 3
    m.away_score = 0
    m.interruption_status = "awarded"
    db.add(PredictionSnapshot(
        match_id="M999", p_home=0.5, p_draw=0.3, p_away=0.2,
        p_over_2_5=0.6, p_btts=0.5, lambda_home=1.4, lambda_away=1.0,
    ))
    db.commit()

    # Redirect calibration_logger to use OUR in-memory session.
    monkeypatch.setattr(calibration_logger, "SessionLocal", lambda: db)
    result = calibration_logger.log_finished_matches()
    assert result["added"] == 0
    assert db.query(ModelCalibrationLog).count() == 0


# ---------------------------------------------------------------------------
# scores.py FD-org guard — refuses to overwrite an interrupted row
# ---------------------------------------------------------------------------


def test_fdorg_writer_skips_interrupted_rows(db, monkeypatch):
    """Reproduces the original bug: football-data.org reports FRA-IRQ as
    FINISHED 1-0 while api-football still has it as INT. With the guard in
    place the partial score must not leak into Match.home_score."""
    from backend.data.fetchers import scores as scores_mod

    m, _ = _make_match(db)
    m.interruption_status = "delayed"
    m.partial_home_score = 1
    m.partial_away_score = 0
    db.commit()

    monkeypatch.setattr(scores_mod, "SessionLocal", lambda: db)
    # Run the writer with a fake FD result that claims FRA-IRQ is FT 1-0.
    import asyncio
    asyncio.run(scores_mod._write_scores_from_fdorg([
        {"home_code": "fr", "away_code": "iq", "home_score": 1, "away_score": 0},
    ]))

    db.expire_all()
    fresh = db.query(Match).filter_by(id="M042").one()
    # Status NOT promoted, FT NOT written.
    assert fresh.status == "upcoming"
    assert fresh.home_score is None
    assert fresh.away_score is None
    assert fresh.interruption_status == "delayed"


# ---------------------------------------------------------------------------
# Watchdog — age-out abandons matches stuck delayed past the cutoff
# ---------------------------------------------------------------------------


def test_watchdog_constant_is_24h():
    # Guards against silent shortening of the cutoff. 24h matches FIFA's
    # own "resume same or next day" posture — see plan §7d.
    from backend.data.fetchers.live import _DELAYED_TO_ABANDONED_HOURS
    assert _DELAYED_TO_ABANDONED_HOURS == 24
