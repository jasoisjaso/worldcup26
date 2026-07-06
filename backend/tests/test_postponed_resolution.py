"""Regression for the 2026-07-06 MEX-ENG case.

A match POSTPONED *before kickoff* and later replayed on a different slot must be
resolved by the football-data.org score writer. The live api-football poller
cannot resolve it — a pre-kickoff postponement has no LiveMatchState / fixture
id and live.py explicitly excludes status='postponed' from polling — so fd.org
reporting the fixture FINISHED is the ONLY resolution path.

The complementary invariant still holds: a DELAYED/abandoned match that WAS in
play carries a partial scoreline and must NOT be force-FT'd by fd.org (FRA-IRQ).
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.models import Base, Match
import backend.data.fetchers.scores as scores
import backend.data.fetchers.tournament_form as tournament_form


@pytest.fixture()
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    # The writer opens its own session + rebuilds tournament form; point both at
    # the in-memory DB and stub the rebuild (needs unrelated tables/data).
    monkeypatch.setattr(scores, "SessionLocal", Session)
    monkeypatch.setattr(tournament_form, "rebuild", lambda db: None)
    yield Session
    engine.dispose()


def test_postponed_no_partial_is_resolved(session_factory):
    s = session_factory()
    s.add(Match(
        id="M092", home_code="mx", away_code="gb-eng",
        kickoff=datetime(2026, 7, 5, 0, 0, 0),
        status="postponed",
        interruption_status="postponed",
        interruption_reason="api-football status=PST",
    ))
    s.commit()
    s.close()

    asyncio.run(scores._write_scores_from_fdorg([
        {"home_code": "mx", "away_code": "gb-eng", "home_score": 2, "away_score": 3},
    ]))

    s = session_factory()
    m = s.get(Match, "M092")
    assert m.status == "complete"
    assert (m.home_score, m.away_score) == (2, 3)
    assert m.interruption_status is None
    assert m.interruption_reason is None
    s.close()


def test_delayed_with_partial_still_protected(session_factory):
    s = session_factory()
    s.add(Match(
        id="M042", home_code="fr", away_code="iq",
        kickoff=datetime(2026, 6, 22, 21, 0, 0),
        status="upcoming",
        interruption_status="delayed",
        partial_home_score=1, partial_away_score=0,
    ))
    s.commit()
    s.close()

    # fd.org classifies the suspended match as FINISHED 1-0 — must be ignored.
    asyncio.run(scores._write_scores_from_fdorg([
        {"home_code": "fr", "away_code": "iq", "home_score": 1, "away_score": 0},
    ]))

    s = session_factory()
    m = s.get(Match, "M042")
    assert m.status == "upcoming"           # NOT force-completed
    assert m.home_score is None
    assert m.interruption_status == "delayed"
    s.close()


def test_abandoned_replay_on_later_slot_resolves(session_factory):
    # Abandoned at 1-1; replayed the next day and finished 2-0. The fd.org
    # fixture is dated well after the original kickoff → treat as the replay.
    s = session_factory()
    s.add(Match(
        id="M050", home_code="fr", away_code="iq",
        kickoff=datetime(2026, 6, 22, 21, 0, 0),
        status="abandoned",
        interruption_status="abandoned",
        partial_home_score=1, partial_away_score=1,
    ))
    s.commit()
    s.close()

    asyncio.run(scores._write_scores_from_fdorg([
        {"home_code": "fr", "away_code": "iq", "home_score": 2, "away_score": 0,
         "utc_date": "2026-06-23T21:00:00Z"},
    ]))

    s = session_factory()
    m = s.get(Match, "M050")
    assert m.status == "complete"
    assert (m.home_score, m.away_score) == (2, 0)
    assert m.interruption_status is None
    s.close()


def test_abandoned_same_slot_misreport_is_rejected(session_factory):
    # fd.org flips the ORIGINAL abandoned fixture to FINISHED with the partial
    # (same date). Must be ignored — the match stays abandoned/void (FRA-IRQ).
    s = session_factory()
    s.add(Match(
        id="M051", home_code="fr", away_code="iq",
        kickoff=datetime(2026, 6, 22, 21, 0, 0),
        status="abandoned",
        interruption_status="abandoned",
        partial_home_score=1, partial_away_score=0,
    ))
    s.commit()
    s.close()

    asyncio.run(scores._write_scores_from_fdorg([
        {"home_code": "fr", "away_code": "iq", "home_score": 1, "away_score": 0,
         "utc_date": "2026-06-22T21:00:00Z"},
    ]))

    s = session_factory()
    m = s.get(Match, "M051")
    assert m.status == "abandoned"
    assert m.home_score is None
    assert m.interruption_status == "abandoned"
    s.close()


def test_historical_edition_is_rejected(session_factory):
    # Same team pairing, but the fd.org fixture is a past-World-Cup edition
    # dated years before our kickoff → must not overwrite this fixture.
    s = session_factory()
    s.add(Match(
        id="M060", home_code="mx", away_code="gb-eng",
        kickoff=datetime(2026, 7, 5, 0, 0, 0),
        status="upcoming",
    ))
    s.commit()
    s.close()

    asyncio.run(scores._write_scores_from_fdorg([
        {"home_code": "mx", "away_code": "gb-eng", "home_score": 0, "away_score": 4,
         "utc_date": "2018-06-27T18:00:00Z"},
    ]))

    s = session_factory()
    m = s.get(Match, "M060")
    assert m.status == "upcoming"
    assert m.home_score is None
    s.close()
