"""Tests for the harvested-xG attack-form modifier (backend/data/fetchers/team_xg.py).

Pins the two behaviours that keep it safe to ship mid-tournament:
  1. Neutral 1.0 below the minimum archived-fixture sample (no noise injection).
  2. A team averaging materially more xG than the reference gets a capped
     positive nudge; less gets a capped negative one.
"""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "team_xg_test.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("WC26_STATE_DIR", tmp)
    monkeypatch.setenv("WC26_HARVEST", "0")
    import importlib
    import backend.db.session as session
    importlib.reload(session)
    from backend.db import migrate
    session.init_db()
    migrate.run_migrations()
    return session


def _seed_xg(session, team_api_id: int, xgs: list[float]):
    from backend.db.models import FixtureArchive
    db = session.SessionLocal()
    try:
        for i, xg in enumerate(xgs):
            db.add(FixtureArchive(api_fixture_id=1000 + i, team_api_id=team_api_id, xg=xg))
        db.commit()
    finally:
        db.close()


def test_neutral_below_min_sample(db_env, monkeypatch):
    import backend.data.fetchers.team_xg as tx
    monkeypatch.setattr(tx, "SessionLocal", db_env.SessionLocal)
    # 'fr' -> api id 2. Seed only 2 fixtures (below the 3 floor).
    _seed_xg(db_env, 2, [2.5, 2.5])
    h, a = tx.get_xg_form_multipliers("fr", "es")
    assert h == 1.0  # below floor → neutral
    assert a == 1.0  # no data at all → neutral


def test_high_xg_team_gets_positive_capped_nudge(db_env, monkeypatch):
    import backend.data.fetchers.team_xg as tx
    monkeypatch.setattr(tx, "SessionLocal", db_env.SessionLocal)
    # 'fr' averages 2.5 xG (well above the 1.3 reference) over 5 fixtures.
    _seed_xg(db_env, 2, [2.4, 2.6, 2.5, 2.5, 2.5])
    h, _ = tx.get_xg_form_multipliers("fr", "es")
    assert h > 1.0
    assert h <= 1.0 + tx._XG_SCALE + 1e-9  # never exceeds the cap


def test_low_xg_team_gets_negative_capped_nudge(db_env, monkeypatch):
    import backend.data.fetchers.team_xg as tx
    monkeypatch.setattr(tx, "SessionLocal", db_env.SessionLocal)
    # 'es' -> api id 9. Averages 0.4 xG (well below reference).
    _seed_xg(db_env, 9, [0.3, 0.5, 0.4, 0.4, 0.4])
    _, a = tx.get_xg_form_multipliers("fr", "es")
    assert a < 1.0
    assert a >= 1.0 - tx._XG_SCALE - 1e-9  # never below the cap


def test_xg_to_mult_pure_mapping():
    import backend.data.fetchers.team_xg as tx
    assert tx._xg_to_mult(None) == 1.0
    assert tx._xg_to_mult(tx._REFERENCE_XG) == 1.0  # at reference → neutral
    # Far above reference clamps to the positive cap.
    assert tx._xg_to_mult(tx._REFERENCE_XG + 10) == round(1.0 + tx._XG_SCALE, 4)
    # Far below reference clamps to the negative cap.
    assert tx._xg_to_mult(0.0) == round(1.0 - tx._XG_SCALE, 4)
