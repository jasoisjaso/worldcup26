"""Regression for the 2026-07-06 'multi model picks not working' report.

Two coupled bugs stalled the model-multis board:
  1. The /model-multis 'active' list returned ALL pending multis, so a finished
     match whose multi hadn't settled yet showed as a live pick (the stale
     Paraguay v France symptom). `_still_open` must exclude all-finished multis.
  2. generate_daily_picks counted such stale-pending multis toward the daily
     cap, stalling new generation. (Covered by manual verification + the
     live_pending guard; here we lock the display-side invariant.)
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

from backend.db.models import Base, Match, Team, ModelMulti, ModelMultiLeg
from backend.api.routes import model_picks


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    s.add_all([
        Team(code="mx", name="Mexico"), Team(code="gb-eng", name="England"),
        Team(code="pt", name="Portugal"), Team(code="es", name="Spain"),
    ])
    yield s
    s.close()
    engine.dispose()


def _multi(s, mid, legs):
    mm = ModelMulti(id=mid, generated_at=datetime(2026, 7, 6, 6, 0, 0),
                    label="t", kind="sgm", combined_prob=0.2,
                    combined_book_odds=6.0, ev_pct=20.0, kelly_pct=1.0, status="pending")
    s.add(mm)
    s.flush()
    for i, (match_id, market) in enumerate(legs):
        s.add(ModelMultiLeg(multi_id=mm.id, leg_order=i + 1, match_id=match_id,
                            market=market, market_label=market))
    s.commit()
    return mm


def test_finished_multi_excluded_from_active(db):
    # M-done is complete; M-live is still upcoming.
    db.add(Match(id="MD", home_code="mx", away_code="gb-eng",
                 kickoff=datetime(2026, 7, 4, 21, 0, 0), status="complete",
                 home_score=0, away_score=1))
    db.add(Match(id="ML", home_code="pt", away_code="es",
                 kickoff=datetime(2026, 7, 7, 19, 0, 0), status="upcoming"))
    db.commit()

    finished = _multi(db, 1, [("MD", "draw")])         # all legs complete
    live = _multi(db, 2, [("ML", "home_win")])         # still open

    assert model_picks._still_open(db, finished) is False
    assert model_picks._still_open(db, live) is True

    out = asyncio.run(model_picks.list_model_multis(db))
    active_ids = {m["id"] for m in out["active"]}
    assert active_ids == {2}                            # finished one hidden
