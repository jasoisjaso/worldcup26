"""Behaviour tests for /api/push/follow-* endpoints.

Covers the contracts the FE will rely on:
  * follow-match is idempotent (repeat = update, never duplicate)
  * unfollow-match on an auto_pick row sets no_auto_refollow=True
  * subsequent auto_pick follows on a flagged row are suppressed
  * /follows hides no_auto_refollow stubs
  * event-mask PATCH updates either match or team rows
  * follow-* on a missing PushSubscription returns 404
"""
from __future__ import annotations

import os
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.models import Base, PushSubscription, FollowedMatch, FollowedTeam
from backend.db.session import get_db


@pytest.fixture()
def client():
    """FastAPI TestClient wired to an in-memory SQLite + the push router."""
    from fastapi import FastAPI
    from backend.api.routes.push import router as push_router

    # StaticPool + check_same_thread=False — required so the TestClient's
    # request thread can reuse the same in-memory SQLite connection that
    # the seeding step below opened on the main thread.
    engine = create_engine(
        "sqlite:///:memory:",
        future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)

    def _get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app = FastAPI()
    app.include_router(push_router, prefix="/api/push")
    app.dependency_overrides[get_db] = _get_db
    # Seed an existing subscription so the _verify_endpoint gate passes.
    s = Session()
    s.add(PushSubscription(endpoint="ep://device-1", p256dh="x", auth="y"))
    s.commit()
    s.close()
    return TestClient(app), Session


# ---------------------------------------------------------------------------
# follow-match — basic lifecycle
# ---------------------------------------------------------------------------


def test_follow_match_creates_row(client):
    c, Session = client
    r = c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042",
    })
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "created"
    s = Session()
    rows = s.query(FollowedMatch).all()
    assert len(rows) == 1
    assert rows[0].source == "manual"
    assert rows[0].no_auto_refollow is False
    s.close()


def test_follow_match_is_idempotent(client):
    c, Session = client
    c.post("/api/push/follow-match", json={"endpoint": "ep://device-1", "match_id": "M042"})
    r2 = c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "event_mask": 8,
    })
    assert r2.json()["status"] == "updated"
    s = Session()
    rows = s.query(FollowedMatch).all()
    assert len(rows) == 1  # not duplicated
    assert rows[0].event_mask == 8
    s.close()


def test_follow_match_404_when_no_subscription(client):
    c, _ = client
    r = c.post("/api/push/follow-match", json={
        "endpoint": "ep://nonexistent", "match_id": "M042",
    })
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Explicit-unfollow precedence on auto_pick rows
# ---------------------------------------------------------------------------


def test_unfollow_auto_pick_creates_no_refollow_stub(client):
    """User had a pick → we auto-followed → user explicitly unfollows.
    The next time they add a pick to their multi, the auto-follow path
    must be blocked."""
    c, Session = client
    # Add to acca -> auto_pick follow
    c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "source": "auto_pick",
    })
    # User explicitly turns off the bell
    r = c.post("/api/push/unfollow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042",
    })
    assert r.json() == {"status": "unfollowed", "was_auto": True}
    s = Session()
    stub = s.query(FollowedMatch).filter_by(match_id="M042").one()
    assert stub.event_mask == 0
    assert stub.no_auto_refollow is True
    s.close()

    # Next auto-pick attempt is blocked
    r2 = c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "source": "auto_pick",
    })
    assert r2.json()["status"] == "blocked_by_no_auto_refollow"


def test_unfollow_manual_does_not_create_stub(client):
    c, Session = client
    c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042",  # default 'manual'
    })
    r = c.post("/api/push/unfollow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042",
    })
    assert r.json() == {"status": "unfollowed", "was_auto": False}
    s = Session()
    assert s.query(FollowedMatch).count() == 0  # no stub left behind
    s.close()


def test_manual_follow_overrides_existing_auto_pick(client):
    """A user taps the bell on a match they already auto-followed via a
    bet. Source should upgrade to 'manual' so a later unfollow on the
    bet doesn't trigger the no_auto_refollow stub."""
    c, Session = client
    c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "source": "auto_pick",
    })
    c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "source": "manual",
    })
    s = Session()
    assert s.query(FollowedMatch).one().source == "manual"
    s.close()


# ---------------------------------------------------------------------------
# follow-team
# ---------------------------------------------------------------------------


def test_follow_team_lifecycle(client):
    c, Session = client
    c.post("/api/push/follow-team", json={"endpoint": "ep://device-1", "team_code": "fr"})
    s = Session()
    assert s.query(FollowedTeam).count() == 1
    s.close()
    r = c.post("/api/push/unfollow-team", json={"endpoint": "ep://device-1", "team_code": "fr"})
    assert r.json()["status"] == "unfollowed"


# ---------------------------------------------------------------------------
# event-mask PATCH
# ---------------------------------------------------------------------------


def test_update_event_mask_on_match(client):
    c, Session = client
    c.post("/api/push/follow-match", json={"endpoint": "ep://device-1", "match_id": "M042"})
    r = c.patch("/api/push/event-mask", json={
        "endpoint": "ep://device-1", "match_id": "M042", "event_mask": 6,
    })
    assert r.json() == {"status": "updated", "event_mask": 6}


def test_update_event_mask_requires_target(client):
    c, _ = client
    r = c.patch("/api/push/event-mask", json={
        "endpoint": "ep://device-1", "event_mask": 6,
    })
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# /follows listing — must hide the no_auto_refollow stubs
# ---------------------------------------------------------------------------


def test_list_follows_hides_no_refollow_stubs(client):
    c, _ = client
    c.post("/api/push/follow-match", json={"endpoint": "ep://device-1", "match_id": "M001"})
    c.post("/api/push/follow-match", json={
        "endpoint": "ep://device-1", "match_id": "M042", "source": "auto_pick",
    })
    c.post("/api/push/unfollow-match", json={"endpoint": "ep://device-1", "match_id": "M042"})
    c.post("/api/push/follow-team", json={"endpoint": "ep://device-1", "team_code": "fr"})

    r = c.get("/api/push/follows", params={"endpoint": "ep://device-1"})
    body = r.json()
    assert len(body["matches"]) == 1
    assert body["matches"][0]["match_id"] == "M001"
    assert len(body["teams"]) == 1
    assert body["teams"][0]["team_code"] == "fr"
