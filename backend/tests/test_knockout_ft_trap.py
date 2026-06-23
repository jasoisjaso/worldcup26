"""Regression: knockout matches must NOT be marked 'complete' on bare FT.

api-football emits status="FT" for ~30 seconds at the end of regulation in a
knockout match before flipping to BT/ET, exactly the same way a group match
finishes — there is no field distinguishing them. Pre this fix, that FT
window locked Match.status="complete" with the 90' score and the UI showed
a stale "FT 1-1" for the entire 15-30 min of extra time.

Now: a knockout (matchday >= 4) only completes on AET / PEN. Group stage
(matchday 1-3) completes on FT as before.

This also tests the shootout-score capture: when status reaches PEN, we read
score.penalty.{home,away} and persist it onto both LiveMatchState AND Match
so the bracket / report-card readers don't need a join.
"""
from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "knockout_ft_test.db")
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

    # Force-set _API_KEY on the live module. The module reads os.getenv at
    # import time and caches it — if test_match_interruption.py loads live
    # before this test's monkeypatch.setenv, _API_KEY ends up as "" and
    # refresh_live_fixtures returns immediately without doing anything.
    # monkeypatch attrs unwind cleanly between tests.
    from backend.data.fetchers import live as live_module
    monkeypatch.setattr(live_module, "_API_KEY", "TEST_KEY")
    return session


def _seed_knockout(db_env, matchday=4):
    """One knockout fixture: Argentina vs France at the given matchday."""
    from datetime import datetime
    from backend.db.models import Match, Team, PredictionSnapshot

    db = db_env.SessionLocal()
    for code, name in [("ar", "Argentina"), ("fr", "France")]:
        if not db.query(Team).filter(Team.code == code).first():
            db.add(Team(code=code, name=name, flag_url=None, elo=1850.0))
    db.add(Match(id="K001", home_code="ar", away_code="fr",
                 kickoff=datetime.utcnow(), status="in_play",
                 group=None, matchday=matchday))
    db.add(PredictionSnapshot(match_id="K001", lambda_home=1.6, lambda_away=1.5,
                              p_home=0.4, p_draw=0.25, p_away=0.35))
    db.commit()
    db.close()


def _seed_group(db_env):
    """One group-stage fixture, matchday 1 (so FT is still decisive)."""
    from datetime import datetime
    from backend.db.models import Match, Team, PredictionSnapshot
    db = db_env.SessionLocal()
    for code, name in [("ar", "Argentina"), ("fr", "France")]:
        if not db.query(Team).filter(Team.code == code).first():
            db.add(Team(code=code, name=name, flag_url=None, elo=1850.0))
    db.add(Match(id="G001", home_code="ar", away_code="fr",
                 kickoff=datetime.utcnow(), status="in_play",
                 group="A", matchday=1))
    db.add(PredictionSnapshot(match_id="G001", lambda_home=1.5, lambda_away=1.2,
                              p_home=0.5, p_draw=0.25, p_away=0.25))
    db.commit()
    db.close()


def _build_fixture_response(fixture_id, home_api, away_api, status, h_score, a_score,
                            so_home=None, so_away=None, elapsed=90):
    """Build a single-fixture /fixtures?live=all response entry."""
    penalty_block = {}
    if so_home is not None or so_away is not None:
        penalty_block = {"home": so_home, "away": so_away}
    return {
        "response": [{
            "fixture": {"id": fixture_id, "status": {"short": status, "elapsed": elapsed, "extra": 0}},
            "teams": {"home": {"id": home_api}, "away": {"id": away_api}},
            "goals": {"home": h_score, "away": a_score},
            "score": {
                "halftime": {"home": 0, "away": 0},
                "fulltime": {"home": h_score, "away": a_score},
                "extratime": None,
                "penalty": penalty_block if penalty_block else None,
            },
        }]
    }


def _run_one_pass(monkeypatch, db_env, response_payload):
    """Run a single live-poller pass with a stubbed httpx client."""
    import asyncio
    from backend.data.fetchers import live as live_module

    monkeypatch.setattr(live_module, "_fetch_events", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "_fetch_stats_raw", AsyncMock(return_value=[]))
    monkeypatch.setattr(live_module, "SessionLocal", db_env.SessionLocal)
    live_module._FIXTURE_MEMO.clear()

    class _FakeResp:
        status_code = 200
        headers = {}
        def json(self): return response_payload
        @property
        def text(self): return ""
    class _FakeClient:
        def __init__(self, *a, **k): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def get(self, url, params=None, headers=None, timeout=None):
            return _FakeResp()
    monkeypatch.setattr(live_module.httpx, "AsyncClient", _FakeClient)
    asyncio.run(live_module.refresh_live_fixtures())


def test_knockout_ft_does_not_complete(db_env, monkeypatch):
    """The trap: knockout match showing status=FT (regulation done, heading
    to ET) must NOT have Match.status flipped to 'complete'. Pre-fix this
    locked in a stale "1-1 FT" for the entire ET period."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import Match

    _seed_knockout(db_env, matchday=4)
    payload = _build_fixture_response(
        fixture_id=999, home_api=TEAM_IDS["ar"], away_api=TEAM_IDS["fr"],
        status="FT", h_score=1, a_score=1, elapsed=90,
    )
    _run_one_pass(monkeypatch, db_env, payload)

    db = db_env.SessionLocal()
    match = db.query(Match).filter(Match.id == "K001").first()
    # Critical: NOT complete. Should still be in_play awaiting AET/PEN.
    assert match.status != "complete", (
        f"knockout match marked complete on bare FT (regression!): "
        f"status={match.status}"
    )
    assert match.home_score is None  # 90' score must not leak in
    assert match.away_score is None
    db.close()


def test_knockout_aet_does_complete(db_env, monkeypatch):
    """AET (extra time finished, decided in 120') IS decisive on a knockout
    — flips status to complete with the 120' score."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import Match

    _seed_knockout(db_env, matchday=5)
    payload = _build_fixture_response(
        fixture_id=999, home_api=TEAM_IDS["ar"], away_api=TEAM_IDS["fr"],
        status="AET", h_score=2, a_score=1, elapsed=120,
    )
    _run_one_pass(monkeypatch, db_env, payload)

    db = db_env.SessionLocal()
    match = db.query(Match).filter(Match.id == "K001").first()
    assert match.status == "complete"
    assert match.home_score == 2
    assert match.away_score == 1
    assert match.shootout_home_score is None  # no shootout happened
    assert match.shootout_away_score is None
    db.close()


def test_knockout_pen_captures_shootout_score(db_env, monkeypatch):
    """PEN (shootout decided) IS decisive AND captures the shootout score
    from score.penalty. Final scoreline reads as a draw (1-1) and the
    tiebreaker is the 4-3 in shootout_*_score columns."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import Match, LiveMatchState

    _seed_knockout(db_env, matchday=8)  # Final
    payload = _build_fixture_response(
        fixture_id=999, home_api=TEAM_IDS["ar"], away_api=TEAM_IDS["fr"],
        status="PEN", h_score=1, a_score=1, so_home=4, so_away=3, elapsed=120,
    )
    _run_one_pass(monkeypatch, db_env, payload)

    db = db_env.SessionLocal()
    match = db.query(Match).filter(Match.id == "K001").first()
    assert match.status == "complete"
    # Regulation-plus-ET score is still 1-1 (FIFA-official draw).
    assert match.home_score == 1
    assert match.away_score == 1
    # Tiebreaker captured on both Match and LiveMatchState.
    assert match.shootout_home_score == 4
    assert match.shootout_away_score == 3
    lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == "K001").first()
    assert lms.shootout_home_score == 4
    assert lms.shootout_away_score == 3
    db.close()


def test_group_ft_still_completes(db_env, monkeypatch):
    """Sanity: don't regress group-stage matches. matchday 1-3 must still
    flip to complete on FT — only knockout FT is held back."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import Match

    _seed_group(db_env)
    payload = _build_fixture_response(
        fixture_id=999, home_api=TEAM_IDS["ar"], away_api=TEAM_IDS["fr"],
        status="FT", h_score=2, a_score=0, elapsed=90,
    )
    _run_one_pass(monkeypatch, db_env, payload)

    db = db_env.SessionLocal()
    match = db.query(Match).filter(Match.id == "G001").first()
    assert match.status == "complete"
    assert match.home_score == 2
    assert match.away_score == 0
    db.close()


def test_shootout_score_persists_during_progress(db_env, monkeypatch):
    """Status="P" (shootout in progress) — score.penalty updates each tick
    and we mirror it to LiveMatchState so the live UI ball-by-ball tracker
    has fresh data. Match row is NOT yet flipped to complete (status="P"
    isn't decisive — we wait for PEN)."""
    from backend.data.fetchers.injuries import TEAM_IDS
    from backend.db.models import Match, LiveMatchState

    _seed_knockout(db_env, matchday=8)
    # Mid-shootout: 2 kicks each, both teams 2/2.
    payload = _build_fixture_response(
        fixture_id=999, home_api=TEAM_IDS["ar"], away_api=TEAM_IDS["fr"],
        status="P", h_score=1, a_score=1, so_home=2, so_away=2, elapsed=120,
    )
    _run_one_pass(monkeypatch, db_env, payload)

    db = db_env.SessionLocal()
    match = db.query(Match).filter(Match.id == "K001").first()
    assert match.status != "complete"  # shootout still in progress
    lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == "K001").first()
    assert lms.shootout_home_score == 2
    assert lms.shootout_away_score == 2
    db.close()
