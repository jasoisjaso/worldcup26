"""Regression: matchday-3 has two WC fixtures kicking off at the same time.

The live poller pulls /fixtures?live=all in a single call (so it scales
naturally), then iterates each fixture. These tests guard the two places
that *could* cross-contaminate when there's more than one live match:
  - LiveMatchState rows must be one-per-match (no shared row)
  - LiveWpHistory ticks must each carry their own match_id
  - Push dedup keys must include match_id so a goal in one match doesn't
    suppress the notification for a goal in the other

We stub api-football's HTTP layer and let the real refresh_live_fixtures()
run end-to-end against an isolated sqlite DB.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import patch, AsyncMock, MagicMock

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "concurrent_live_test.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("WC26_STATE_DIR", tmp)
    monkeypatch.setenv("WC26_HARVEST", "0")
    monkeypatch.setenv("API_FOOTBALL_KEY", "TEST_KEY")

    import importlib
    import backend.db.session as session
    importlib.reload(session)
    from backend.db import migrate

    session.init_db()
    migrate.run_migrations()
    return session


def _seed_two_simultaneous_matches(db_env):
    """Two upcoming WC fixtures kicking off right now with predictions ready."""
    from datetime import datetime
    from backend.db.models import Match, Team, PredictionSnapshot

    db = db_env.SessionLocal()
    now = datetime.utcnow()
    # Insert dummy teams using the same 2-letter codes the TEAM_IDS map uses.
    for code, name in [("ar", "Argentina"), ("at", "Austria"),
                       ("br", "Brazil"), ("kr", "South Korea")]:
        db.add(Team(code=code, name=name, flag_url=None, elo=1600.0))
    db.add(Match(id="M001", home_code="ar", away_code="at",
                 kickoff=now, status="in_play", group="A", matchday=3))
    db.add(Match(id="M002", home_code="br", away_code="kr",
                 kickoff=now, status="in_play", group="B", matchday=3))
    # Prediction snapshots — the poller skips ticks without lambda values.
    db.add(PredictionSnapshot(match_id="M001", lambda_home=1.8, lambda_away=0.9,
                              p_home=0.6, p_draw=0.2, p_away=0.2))
    db.add(PredictionSnapshot(match_id="M002", lambda_home=2.1, lambda_away=0.8,
                              p_home=0.7, p_draw=0.15, p_away=0.15))
    db.commit()
    db.close()


def _stub_live_fixtures_response(arg_score, aut_score, bra_score, kor_score):
    """Build a fake /fixtures?live=all response with two live games."""
    return {
        "response": [
            {
                "fixture": {"id": 101, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": 26}, "away": {"id": 26}},  # team ids set below
                "goals": {"home": arg_score, "away": aut_score},
            },
            {
                "fixture": {"id": 202, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": 6}, "away": {"id": 18}},
                "goals": {"home": bra_score, "away": kor_score},
            },
        ]
    }


def test_two_simultaneous_matches_get_independent_state(db_env, monkeypatch):
    """Two live fixtures must produce two LiveMatchState rows, two history
    ticks, and never share a row."""
    import asyncio
    from backend.data.fetchers import live as live_module
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import LiveMatchState, LiveWpHistory

    # Wire team ids into the fake response so _resolve_match can map them.
    arg_id, aut_id = TEAM_IDS["ar"], TEAM_IDS["at"]
    bra_id, kor_id = TEAM_IDS["br"], TEAM_IDS["kr"]
    fake = {
        "response": [
            {
                "fixture": {"id": 101, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": arg_id}, "away": {"id": aut_id}},
                "goals": {"home": 1, "away": 0},
            },
            {
                "fixture": {"id": 202, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": bra_id}, "away": {"id": kor_id}},
                "goals": {"home": 2, "away": 0},
            },
        ]
    }
    _seed_two_simultaneous_matches(db_env)

    # Stub the per-fixture detail calls (events/stats/lineups) so the poller
    # has nothing surprising to chew on.
    monkeypatch.setattr(live_module, "_fetch_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "_fetch_stats_raw", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "SessionLocal", db_env.SessionLocal)

    # Stub the top-level httpx.AsyncClient so refresh_live_fixtures sees our payload.
    class _FakeResp:
        status_code = 200
        headers = {}
        def json(self): return fake
        @property
        def text(self): return ""
    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None, timeout=None):
            return _FakeResp()
    monkeypatch.setattr(live_module.httpx, "AsyncClient", _FakeClient)
    # Reset memoised fixture mapping — could be polluted from earlier runs.
    live_module._FIXTURE_MEMO.clear()

    asyncio.run(live_module.refresh_live_fixtures())

    db = db_env.SessionLocal()
    states = db.query(LiveMatchState).all()
    state_by_match = {s.match_id: s for s in states}
    assert set(state_by_match.keys()) == {"M001", "M002"}, \
        f"expected two live rows, got {sorted(state_by_match)}"

    # Each row must reflect its OWN score, not the other match's.
    assert state_by_match["M001"].home_score == 1 and state_by_match["M001"].away_score == 0
    assert state_by_match["M002"].home_score == 2 and state_by_match["M002"].away_score == 0
    assert state_by_match["M001"].fixture_id_external == 101
    assert state_by_match["M002"].fixture_id_external == 202

    # And one WP history tick per match.
    hist_m1 = db.query(LiveWpHistory).filter(LiveWpHistory.match_id == "M001").all()
    hist_m2 = db.query(LiveWpHistory).filter(LiveWpHistory.match_id == "M002").all()
    assert len(hist_m1) == 1
    assert len(hist_m2) == 1
    assert hist_m1[0].home_score == 1
    assert hist_m2[0].home_score == 2
    db.close()


def test_push_dedup_key_includes_match_id(db_env, monkeypatch):
    """A simultaneous goal-swing in BOTH matches must produce TWO push
    notifications with distinct dedup_keys — never one collapsing the other."""
    import asyncio
    from backend.data.fetchers import live as live_module
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import LiveWpHistory

    arg_id, aut_id = TEAM_IDS["ar"], TEAM_IDS["at"]
    bra_id, kor_id = TEAM_IDS["br"], TEAM_IDS["kr"]

    _seed_two_simultaneous_matches(db_env)

    # Seed one prior tick per match so the "swing" detector has a previous
    # value to compare against.
    db = db_env.SessionLocal()
    db.add(LiveWpHistory(match_id="M001", elapsed_min=74, p_home=0.55,
                         p_draw=0.25, p_away=0.20, home_score=0, away_score=0))
    db.add(LiveWpHistory(match_id="M002", elapsed_min=74, p_home=0.60,
                         p_draw=0.22, p_away=0.18, home_score=0, away_score=0))
    db.commit()
    db.close()

    # Both fixtures now have a goal — should trigger a swing in each.
    fake = {
        "response": [
            {
                "fixture": {"id": 101, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": arg_id}, "away": {"id": aut_id}},
                "goals": {"home": 1, "away": 0},
            },
            {
                "fixture": {"id": 202, "status": {"short": "2H", "elapsed": 75, "extra": 0}},
                "teams": {"home": {"id": bra_id}, "away": {"id": kor_id}},
                "goals": {"home": 1, "away": 0},
            },
        ]
    }

    monkeypatch.setattr(live_module, "_fetch_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "_fetch_stats_raw", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "SessionLocal", db_env.SessionLocal)

    class _FakeResp:
        status_code = 200
        headers = {}
        def json(self): return fake
        @property
        def text(self): return ""
    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None, timeout=None):
            return _FakeResp()
    monkeypatch.setattr(live_module.httpx, "AsyncClient", _FakeClient)
    live_module._FIXTURE_MEMO.clear()

    # Intercept send_push from where the poller imports it.
    sent_calls = []
    fake_send = MagicMock()
    def _capture(*args, **kw):
        sent_calls.append(kw)
        return None
    fake_send.side_effect = _capture
    with patch("backend.api.routes.push.send_push", fake_send):
        asyncio.run(live_module.refresh_live_fixtures())

    # We expect a push for EACH match (both swing big enough on a 0-0 → 1-0 jump).
    dedup_keys = [c.get("dedup_key", "") for c in sent_calls]
    assert any("M001" in k for k in dedup_keys), \
        f"M001 swing push missing: keys={dedup_keys}"
    assert any("M002" in k for k in dedup_keys), \
        f"M002 swing push missing: keys={dedup_keys}"
    # And the two keys must be distinct so neither suppresses the other.
    keys_per_match = {
        "M001": [k for k in dedup_keys if "M001" in k],
        "M002": [k for k in dedup_keys if "M002" in k],
    }
    assert keys_per_match["M001"] != keys_per_match["M002"]
