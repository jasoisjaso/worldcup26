"""The fd.org score writer must record a result even when the source lists the fixture
with home/away reversed relative to our schedule row, swapping the scores back."""
import asyncio

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.models import Base, Match
from backend.data.fetchers import scores as scores_mod


def _memory_sessionmaker():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)


def _run_writer(monkeypatch, seed_matches, results):
    SessionFactory = _memory_sessionmaker()
    monkeypatch.setattr(scores_mod, "SessionLocal", SessionFactory)
    # The writer rebuilds the tournament-form cache on success; stub it out — not under test.
    import backend.data.fetchers.tournament_form as tf
    monkeypatch.setattr(tf, "rebuild", lambda db: None)

    db = SessionFactory()
    for m in seed_matches:
        db.add(Match(**m))
    db.commit()
    db.close()

    asyncio.run(scores_mod._write_scores_from_fdorg(results))

    db = SessionFactory()
    rows = {m.id: m for m in db.query(Match).all()}
    db.close()
    return rows


def test_same_orientation_records_directly(monkeypatch):
    rows = _run_writer(
        monkeypatch,
        [{"id": "M1", "home_code": "ARG", "away_code": "BRA", "status": "upcoming"}],
        [{"home_code": "ARG", "away_code": "BRA", "home_score": 2, "away_score": 1}],
    )
    m = rows["M1"]
    assert m.status == "complete"
    assert (m.home_score, m.away_score) == (2, 1)


def test_reversed_orientation_swaps_scores(monkeypatch):
    # Our row is ARG (home) vs BRA (away); fd.org lists BRA home 1 - ARG away 2.
    # ARG actually won 2-1, so our row must read home=2, away=1 after the swap.
    rows = _run_writer(
        monkeypatch,
        [{"id": "M1", "home_code": "ARG", "away_code": "BRA", "status": "upcoming"}],
        [{"home_code": "BRA", "away_code": "ARG", "home_score": 1, "away_score": 2}],
    )
    m = rows["M1"]
    assert m.status == "complete"
    assert (m.home_score, m.away_score) == (2, 1)


def test_unknown_fixture_is_left_untouched(monkeypatch):
    rows = _run_writer(
        monkeypatch,
        [{"id": "M1", "home_code": "ARG", "away_code": "BRA", "status": "upcoming"}],
        [{"home_code": "ESP", "away_code": "GER", "home_score": 3, "away_score": 0}],
    )
    m = rows["M1"]
    assert m.status == "upcoming"
    assert m.home_score is None
