"""Regression test for the /transfers harvest path.

Guards the wiring fixed 2026-06-22: the transfers normaliser was built and
routed but never enqueued, and it only read the player id from the job param
(so a team-scoped response would mis-attribute every transfer to player 0).
This test pins both halves: team-scoped attribution from the response body,
and the fan-out enqueueing /transfers per discovered team.
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    """Spin up an isolated sqlite DB so the test never touches prod data."""
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "transfers_test.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("WC26_STATE_DIR", tmp)
    monkeypatch.setenv("WC26_HARVEST", "0")  # never let any real call fire

    # Import after env is set so the engine binds to the temp DB.
    import importlib

    import backend.db.session as session
    importlib.reload(session)
    from backend.db import migrate

    session.init_db()
    migrate.run_migrations()
    return session


def test_team_scoped_transfers_attribute_to_each_player(db_env, monkeypatch):
    import backend.data.harvest_processor as hp
    from backend.db.models import HarvestJob, HarvestRaw, PlayerTransfer

    # Point the processor's SessionLocal at the freshly-bound engine.
    monkeypatch.setattr(hp, "SessionLocal", db_env.SessionLocal)

    db = db_env.SessionLocal()
    job = HarvestJob(endpoint="/transfers", params_json=json.dumps({"team": 768}), status="done")
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "response": [
            {
                "player": {"id": 101, "name": "Player One"},
                "transfers": [
                    {"date": "2026-01-15", "type": "€10M",
                     "teams": {"out": {"id": 1, "name": "Old FC"},
                               "in": {"id": 768, "name": "New FC"}}},
                ],
            },
            {
                "player": {"id": 202, "name": "Player Two"},
                "transfers": [
                    {"date": "2025-08-01", "type": "Loan",
                     "teams": {"out": {"id": 768, "name": "New FC"},
                               "in": {"id": 9, "name": "Loan FC"}}},
                ],
            },
        ]
    }
    raw = HarvestRaw(
        job_id=job.id,
        endpoint="/transfers",
        status_code=200,
        response_json=json.dumps(payload),
        processed=False,
    )
    db.add(raw)
    db.commit()
    db.refresh(raw)
    db.close()

    written = hp._normalise_transfers(raw)
    assert written == 2

    db = db_env.SessionLocal()
    rows = {r.player_api_id: r for r in db.query(PlayerTransfer).all()}
    db.close()

    # Each transfer attributed to the player in its own entry, NOT player 0.
    assert set(rows) == {101, 202}
    assert rows[101].player_name == "Player One"
    assert rows[101].to_team_name == "New FC"
    assert rows[202].transfer_type == "Loan"


def test_fixtures_fanout_enqueues_transfers(db_env, monkeypatch):
    """The /fixtures processor must fan out a /transfers job per discovered team."""
    import backend.data.harvest_processor as hp
    from backend.db.models import HarvestJob, HarvestRaw

    monkeypatch.setattr(hp, "SessionLocal", db_env.SessionLocal)

    enqueued: list[tuple[str, dict]] = []

    def _fake_enqueue(endpoint, params, priority=100):
        enqueued.append((endpoint, params))
        return True

    monkeypatch.setattr(hp, "_harvest_enqueue", _fake_enqueue)

    db = db_env.SessionLocal()
    job = HarvestJob(endpoint="/fixtures", params_json=json.dumps({"league": 1, "season": 2026}), status="done")
    db.add(job)
    db.commit()
    db.refresh(job)

    payload = {
        "response": [
            {
                "fixture": {"id": 555, "status": {"short": "FT"}},
                "league": {"id": 1, "season": 2026},
                "teams": {"home": {"id": 10}, "away": {"id": 20}},
            }
        ]
    }
    raw = HarvestRaw(
        job_id=job.id,
        endpoint="/fixtures",
        status_code=200,
        response_json=json.dumps(payload),
        processed=False,
    )
    db.add(raw)
    db.commit()
    db.refresh(raw)
    db.close()

    hp._normalise_fixtures(raw)

    transfers_enq = [p for (ep, p) in enqueued if ep == "/transfers"]
    assert {"team": 10} in transfers_enq
    assert {"team": 20} in transfers_enq
