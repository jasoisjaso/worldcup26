"""Tests for the squad-availability modifier (sidelined + continuity).

Pins: neutral when no harvested data, capped penalty when multiple players are
sidelined, and that the cap is never exceeded.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "avail_test.db")
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


def _add_sidelined(session, team_api_id: int, n: int, future: bool = True):
    from backend.db.models import PlayerSidelined
    db = session.SessionLocal()
    try:
        end = datetime.utcnow() + timedelta(days=30) if future else datetime.utcnow() - timedelta(days=30)
        for i in range(n):
            db.add(PlayerSidelined(player_api_id=5000 + i, team_api_id=team_api_id, end_date=end))
        db.commit()
    finally:
        db.close()


def test_neutral_with_no_data(db_env, monkeypatch):
    import backend.data.fetchers.squad_availability as sa
    monkeypatch.setattr(sa, "SessionLocal", db_env.SessionLocal)
    h, a = sa.get_squad_availability_multipliers("fr", "es")
    assert h == 1.0 and a == 1.0


def test_sidelined_players_penalise_and_cap(db_env, monkeypatch):
    import backend.data.fetchers.squad_availability as sa
    monkeypatch.setattr(sa, "SessionLocal", db_env.SessionLocal)
    # 'fr' -> 2. Two active sidelined players → small penalty.
    _add_sidelined(db_env, 2, 2)
    h, _ = sa.get_squad_availability_multipliers("fr", "es")
    assert h < 1.0
    assert h >= 1.0 - sa._CAP - 1e-9

    # Many sidelined → still capped, never below the floor.
    _add_sidelined(db_env, 2, 20)
    h2, _ = sa.get_squad_availability_multipliers("fr", "es")
    assert h2 == round(1.0 - sa._CAP, 4)


def test_expired_sidelined_ignored(db_env, monkeypatch):
    import backend.data.fetchers.squad_availability as sa
    monkeypatch.setattr(sa, "SessionLocal", db_env.SessionLocal)
    # 'es' -> 9. Sidelined players whose end_date already passed don't count.
    _add_sidelined(db_env, 9, 3, future=False)
    _, a = sa.get_squad_availability_multipliers("fr", "es")
    assert a == 1.0
