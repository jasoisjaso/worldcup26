"""Smoke test for GET /matches/{id}/key-players.

Mounts only the predictions router on a minimal FastAPI app so the test never
imports the full main.py (which transitively pulls every optional dep). We
don't pin specific players — the dataset evolves — but we DO assert the
shape, the goalkeeper-exclusion rule, the minutes floor, and the per-side
sort (highest G/90 + A/90 first).
"""
from __future__ import annotations

import os

os.environ.setdefault("WC26_STATE_DIR", "/tmp/wc26_test_state")
os.makedirs(os.environ["WC26_STATE_DIR"], exist_ok=True)

import pytest  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


def _build_app() -> FastAPI:
    from backend.api.routes.predictions import router as predictions_router
    from backend.api.routes.matches import router as matches_router
    from backend.db.session import init_db
    from backend.db.migrate import run_migrations
    from backend.db.seed import seed
    from backend.data.importers.wc2026_per90 import ensure_per90_loaded

    init_db()
    run_migrations()
    seed()
    ensure_per90_loaded()
    app = FastAPI()
    app.include_router(matches_router, prefix="/matches")
    app.include_router(predictions_router, prefix="/matches")
    return app


@pytest.fixture(scope="module")
def client():
    app = _build_app()
    with TestClient(app) as c:
        yield c


def _first_match_id(client: TestClient) -> str | None:
    r = client.get("/matches")
    if r.status_code != 200:
        return None
    rows = r.json()
    return rows[0]["id"] if rows else None


def test_key_players_shape(client):
    mid = _first_match_id(client)
    if not mid:
        pytest.skip("no matches seeded in this checkout")
    r = client.get(f"/matches/{mid}/key-players")
    assert r.status_code == 200
    body = r.json()
    assert body["match_id"] == mid
    assert "home" in body and isinstance(body["home"], list)
    assert "away" in body and isinstance(body["away"], list)
    assert "Rising Transfers" in body["attribution"]

    for side in ("home", "away"):
        assert len(body[side]) <= 3
        for p in body[side]:
            assert "goalkeep" not in (p["position"] or "").lower()
            assert (p["minutes"] or 0) >= 600
            g = p["goals_per90"] or 0
            a = p["assists_per90"] or 0
            assert g > 0 or a > 0
        scores = [
            (p["goals_per90"] or 0) * 1.5 + (p["assists_per90"] or 0)
            for p in body[side]
        ]
        assert scores == sorted(scores, reverse=True)


def test_key_players_unknown_match_returns_404(client):
    r = client.get("/matches/DOES-NOT-EXIST/key-players")
    assert r.status_code == 404
