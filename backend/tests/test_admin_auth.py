"""Verify the bearer-token gate refuses unset/wrong tokens and accepts the right one.

Mounts the harvester router on a minimal FastAPI app so the test never imports
the full main.py (which transitively pulls every optional dep). Anything that
lets the harvester surface leak out is a real incident — the seed actions cost
api-football quota.
"""
from __future__ import annotations

import os

# Ensure /app/data isn't used by the tests — the quota_budget module writes a
# state file to WC26_STATE_DIR on import. Tests run as a non-root user.
os.environ.setdefault("WC26_STATE_DIR", "/tmp/wc26_test_state")
os.makedirs(os.environ["WC26_STATE_DIR"], exist_ok=True)

# Set the admin token BEFORE the app imports so the dependency reads it.
os.environ["WC26_ADMIN_TOKEN"] = "test-admin-secret"

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.api.routes.harvester_admin import router  # noqa: E402
from backend.db.session import init_db  # noqa: E402
from backend.db.migrate import run_migrations  # noqa: E402


def _build_app() -> FastAPI:
    init_db()
    run_migrations()
    app = FastAPI()
    app.include_router(router, prefix="/harvester")
    return app


@pytest.fixture
def client():
    app = _build_app()
    with TestClient(app) as c:
        yield c


def test_status_rejects_missing_token(client):
    r = client.get("/harvester/status")
    assert r.status_code == 401


def test_status_rejects_wrong_token(client):
    r = client.get("/harvester/status", headers={"X-Admin-Token": "nope"})
    assert r.status_code == 401


def test_status_accepts_bearer_header(client):
    r = client.get(
        "/harvester/status",
        headers={"Authorization": "Bearer test-admin-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "by_status" in body


def test_status_accepts_short_form_header(client):
    r = client.get(
        "/harvester/status",
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert r.status_code == 200


def test_overview_returns_expected_shape(client):
    r = client.get(
        "/harvester/overview",
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("queue", "raw_blobs", "tables", "throughput_24h", "quota_budget", "feeds", "caches", "inventory", "settings", "build"):
        assert key in body, f"missing {key} from /harvester/overview"
    # Inventory must expose the coverage cards + endpoint breakdown + activity sparkline.
    inv = body["inventory"]
    for key in ("coverage", "endpoint_breakdown", "activity_7d", "archive_bytes"):
        assert key in inv, f"inventory missing {key}"
    assert len(inv["activity_7d"]) == 7, "activity_7d should always emit 7 padded days"
    # Quota summary must surface the new dashboard fields (FE reads them).
    qb_sum = body["quota_budget"]
    for key in ("live_reserve_floor", "burn_buffer", "burn_window_minutes", "burn_should_fire", "per_minute_remaining", "daily_quota"):
        assert key in qb_sum, f"quota_budget missing {key}"
    assert qb_sum["live_reserve_floor"] == 1250
    assert qb_sum["burn_buffer"] == 100
    assert qb_sum["burn_window_minutes"] == 50


def test_inventory_endpoint_returns_expected_shape(client):
    r = client.get(
        "/harvester/inventory",
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("coverage", "endpoint_breakdown", "activity_7d", "archive_bytes"):
        assert key in body
    # Coverage cards are the user-visible promise of "what we have vs what we want".
    cov_keys = {c["key"] for c in body["coverage"]}
    assert {"wc_squads", "wc_players", "fixture_archive"}.issubset(cov_keys)


def test_pause_resume_round_trip(client):
    r = client.post(
        "/harvester/pause",
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert r.status_code == 200
    assert r.json()["paused"] is True
    # quota_budget.harvester_enabled() should now see the runtime row.
    from backend.data import quota_budget as qb
    assert qb.harvester_enabled() is False

    r2 = client.post(
        "/harvester/resume",
        headers={"X-Admin-Token": "test-admin-secret"},
    )
    assert r2.status_code == 200
    assert r2.json()["paused"] is False
    assert qb.harvester_enabled() is True


def test_admin_gate_returns_503_when_token_unset(monkeypatch):
    """When WC26_ADMIN_TOKEN is missing, the gate must 503 — never accept blank."""
    monkeypatch.delenv("WC26_ADMIN_TOKEN", raising=False)
    app = _build_app()
    with TestClient(app) as c:
        r = c.get("/harvester/status", headers={"X-Admin-Token": ""})
        assert r.status_code == 503
        r2 = c.get("/harvester/status", headers={"X-Admin-Token": "anything"})
        assert r2.status_code == 503
