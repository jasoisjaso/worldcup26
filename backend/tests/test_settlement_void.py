"""Locks down the pick-void rule for interrupted matches.

When a match carries any non-NULL interruption_status (delayed, postponed,
abandoned, awarded), every settlement site MUST refuse to grade picks
against it. The rule mirrors bet365 / Betfair / Sky / Paddy Power — see
docs/plans/2026-06-23_match-interruption-handling.md §7b for sources.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.models import Base, Match, Prediction, ModelMulti, ModelMultiLeg
from backend.betting.settlement_rules import pick_voided, pick_settle_able


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def _match(db, mid="M042", status="upcoming", interruption=None, hs=None, as_=None):
    m = Match(
        id=mid, home_code="fr", away_code="iq",
        kickoff=datetime(2026, 6, 22, 21, 0, 0),
        status=status,
        home_score=hs, away_score=as_,
        interruption_status=interruption,
    )
    db.add(m)
    db.commit()
    return m


# ---------------------------------------------------------------------------
# settlement_rules.py — the central gate
# ---------------------------------------------------------------------------


def test_pick_voided_returns_false_for_none(db):
    assert pick_voided(None) is False
    assert pick_settle_able(None) is False


def test_pick_voided_for_each_interruption(db):
    for s in ("delayed", "postponed", "abandoned", "awarded"):
        m = _match(db, mid=f"M-{s}", interruption=s)
        assert pick_voided(m) is True, f"{s} must void"
        assert pick_settle_able(m) is False, f"{s} must NOT be settle-able"


def test_normal_complete_match_is_settle_able_and_not_voided(db):
    m = _match(db, status="complete", hs=1, as_=0)
    assert pick_voided(m) is False
    assert pick_settle_able(m) is True


def test_complete_match_with_null_scores_is_not_settle_able(db):
    m = _match(db, status="complete", hs=None, as_=None)
    assert pick_settle_able(m) is False


def test_upcoming_match_is_neither(db):
    m = _match(db)
    assert pick_voided(m) is False
    assert pick_settle_able(m) is False


# ---------------------------------------------------------------------------
# history.py _settle_result — returns "void" for interrupted matches
# ---------------------------------------------------------------------------


def test_settle_result_returns_void_for_interrupted(db):
    from backend.api.routes.history import _settle_result, _is_correct
    m = _match(db, status="upcoming", interruption="delayed")
    pred = Prediction(
        match_id=m.id, market="home_win",
        our_probability=0.6, bookmaker_odds=2.1, ev=0.05,
    )
    assert _settle_result(pred, m) == "void"
    # _is_correct must return None for void so accuracy/ROI don't count it.
    assert _is_correct(pred, m) is None


def test_settle_result_still_grades_a_normal_complete_match(db):
    from backend.api.routes.history import _settle_result, _is_correct
    m = _match(db, status="complete", hs=2, as_=1)
    pred = Prediction(
        match_id=m.id, market="home_win",
        our_probability=0.6, bookmaker_odds=2.1, ev=0.05,
    )
    assert _settle_result(pred, m) == "win"
    assert _is_correct(pred, m) is True


# ---------------------------------------------------------------------------
# multi_picker.settle_finished_multis — voids the whole multi on any voided leg
# ---------------------------------------------------------------------------


def test_multi_voids_when_any_leg_match_is_interrupted(db, monkeypatch):
    """Reproduces a parlay including FRA-IRQ: even if the other leg is a
    won FT result, the interrupted leg short-circuits the whole multi
    to void per industry rules."""
    from backend.betting import multi_picker

    # Two legs: one complete winner, one interrupted (FRA-IRQ-style).
    won_match = _match(db, mid="M001", status="complete", hs=3, as_=1)
    int_match = _match(db, mid="M042", interruption="delayed")

    mm = ModelMulti(
        label="test", kind="cross",
        combined_prob=0.4, combined_fair_odds=2.5,
        combined_book_odds=3.0, ev_pct=8.0, kelly_pct=0.04,
        status="pending",
    )
    db.add(mm)
    db.commit()
    db.add_all([
        ModelMultiLeg(multi_id=mm.id, match_id="M001", market="home_win", model_prob=0.6, book_odds=2.0),
        ModelMultiLeg(multi_id=mm.id, match_id="M042", market="home_win", model_prob=0.7, book_odds=1.5),
    ])
    db.commit()

    monkeypatch.setattr(multi_picker, "SessionLocal", lambda: db)
    summary = multi_picker.settle_finished_multis()

    db.expire_all()
    settled = db.query(ModelMulti).filter_by(id=mm.id).one()
    assert settled.status == "void", f"interrupted leg must void parlay, got {settled.status}"
    assert settled.profit_loss_units == 0.0
    assert summary["void"] == 1
    assert summary["won"] == 0
    assert summary["lost"] == 0


def test_multi_settles_normally_when_no_leg_interrupted(db, monkeypatch):
    from backend.betting import multi_picker
    _match(db, mid="MA", status="complete", hs=2, as_=0)
    _match(db, mid="MB", status="complete", hs=1, as_=0)
    mm = ModelMulti(
        label="test-clean", kind="cross",
        combined_prob=0.4, combined_fair_odds=2.5,
        combined_book_odds=3.0, ev_pct=8.0, kelly_pct=0.04,
        status="pending",
    )
    db.add(mm)
    db.commit()
    db.add_all([
        ModelMultiLeg(multi_id=mm.id, match_id="MA", market="home_win", model_prob=0.6, book_odds=2.0),
        ModelMultiLeg(multi_id=mm.id, match_id="MB", market="home_win", model_prob=0.7, book_odds=1.5),
    ])
    db.commit()
    monkeypatch.setattr(multi_picker, "SessionLocal", lambda: db)
    summary = multi_picker.settle_finished_multis()
    db.expire_all()
    settled = db.query(ModelMulti).filter_by(id=mm.id).one()
    assert settled.status == "won"
    assert summary["won"] == 1
