"""Behaviour tests for backend.data.push_dispatch.

Each test stubs `send_push` so we don't need real VAPID keys / network;
we assert the dispatcher built the right recipient list, dedup key,
title, and body. Schema invariants (event_key UNIQUE) live in
test_push_follow_schema.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.db.models import (
    Base, Match, MatchEvent, LiveMatchState, PushSubscription,
    FollowedMatch, FollowedTeam, NotificationEventLog, Team,
)


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", future=True,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    # Seed teams + a match + a live state in the lookback window.
    s.add_all([
        Team(code="fr", name="France"),
        Team(code="iq", name="Iraq"),
        PushSubscription(endpoint="ep://A", p256dh="x", auth="y"),
        PushSubscription(endpoint="ep://B", p256dh="x", auth="y"),
    ])
    m = Match(
        id="M042", home_code="fr", away_code="iq",
        kickoff=datetime.utcnow() - timedelta(minutes=70),
        status="upcoming",
    )
    s.add(m)
    s.add(LiveMatchState(
        match_id="M042", fixture_id_external=999,
        status="2H", elapsed_min=70, home_score=1, away_score=0,
        updated_at=datetime.utcnow(),
    ))
    s.commit()
    yield s, Session
    s.close()
    engine.dispose()


@pytest.fixture()
def patch_dispatcher(db, monkeypatch):
    """Point push_dispatch's SessionLocal AND stub send_push so we capture
    every call instead of hitting pywebpush."""
    _, Session = db
    from backend.data import push_dispatch as pd
    from backend.api.routes import push as push_mod

    captured: list[dict] = []

    def fake_send_push(_db, *, title, body, url, recipients=None, **kw):
        captured.append({
            "title": title, "body": body, "url": url,
            "recipients": list(recipients or []),
        })
        return {"status": "ok", "sent": len(recipients or [])}

    monkeypatch.setattr(pd, "SessionLocal", Session)
    monkeypatch.setattr(push_mod, "send_push", fake_send_push)
    return captured


# ---------------------------------------------------------------------------
# Recipient resolution — _endpoints_for
# ---------------------------------------------------------------------------


def test_endpoints_for_unions_match_and_team(db):
    s, _ = db
    s.add_all([
        FollowedMatch(endpoint="ep://A", match_id="M042"),    # mask default
        FollowedTeam(endpoint="ep://B", team_code="fr"),
    ])
    s.commit()

    from backend.data.push_dispatch import _endpoints_for
    from backend.data import push_events as pe
    match = s.query(Match).filter_by(id="M042").one()

    eps = _endpoints_for(s, match, pe.GOAL, "goal")
    assert set(eps) == {"ep://A", "ep://B"}


def test_endpoints_for_excludes_users_without_mask_bit(db):
    s, _ = db
    # User A subscribed but turned OFF goal alerts (mask without GOAL bit)
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042",
                        event_mask=pe_no_goal()))
    s.commit()

    from backend.data.push_dispatch import _endpoints_for
    from backend.data import push_events as pe
    match = s.query(Match).filter_by(id="M042").one()

    assert _endpoints_for(s, match, pe.GOAL, "goal") == []
    assert _endpoints_for(s, match, pe.RED_CARD, "red_card") == ["ep://A"]


def pe_no_goal():
    from backend.data import push_events as pe
    return pe.DEFAULT_MASK & ~pe.GOAL


def test_always_on_events_bypass_mask(db):
    """Suspended / resumed pings everyone who follows the match, even if
    their event_mask has every bit off."""
    s, _ = db
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042", event_mask=1))  # tiny mask
    s.commit()

    from backend.data.push_dispatch import _endpoints_for
    match = s.query(Match).filter_by(id="M042").one()
    eps = _endpoints_for(s, match, None, "suspended")
    assert eps == ["ep://A"]


def test_always_on_skips_no_auto_refollow_stubs(db):
    """An 'unfollowed bet auto-pick' user (mask=0 stub) should NOT receive
    even the always-on suspended/resumed events — they explicitly opted out."""
    s, _ = db
    s.add(FollowedMatch(
        endpoint="ep://A", match_id="M042",
        event_mask=0, source="manual", no_auto_refollow=True,
    ))
    s.commit()
    from backend.data.push_dispatch import _endpoints_for
    match = s.query(Match).filter_by(id="M042").one()
    assert _endpoints_for(s, match, None, "suspended") == []


# ---------------------------------------------------------------------------
# Goal dispatch — confirms 30s queue, dedup, title/body shape
# ---------------------------------------------------------------------------


def test_goal_skipped_when_too_fresh(db, patch_dispatcher):
    s, _ = db
    s.add_all([
        FollowedMatch(endpoint="ep://A", match_id="M042"),
        MatchEvent(
            match_id="M042", elapsed=67, type="Goal", detail="Normal Goal",
            player_id=10, player_name="Mbappe", team_id=1, team_name="France",
            captured_at=datetime.utcnow(),  # NOW — too fresh
        ),
    ])
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    assert len(patch_dispatcher) == 0, "goal must wait 30s before notifying"


def test_goal_fires_after_confirm_delay(db, patch_dispatcher):
    s, _ = db
    s.add_all([
        FollowedMatch(endpoint="ep://A", match_id="M042"),
        FollowedTeam(endpoint="ep://B", team_code="iq"),  # follow Iraq -> still gets the goal
        MatchEvent(
            match_id="M042", elapsed=67, type="Goal", detail="Normal Goal",
            player_id=10, player_name="Mbappe", team_id=1, team_name="France",
            captured_at=datetime.utcnow() - timedelta(seconds=45),  # > 30s ago
        ),
    ])
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    assert len(patch_dispatcher) == 1
    push = patch_dispatcher[0]
    assert "GOAL" in push["title"]
    assert "Mbappe" in push["body"]
    assert set(push["recipients"]) == {"ep://A", "ep://B"}


def test_goal_dispatched_only_once(db, patch_dispatcher):
    s, _ = db
    s.add_all([
        FollowedMatch(endpoint="ep://A", match_id="M042"),
        MatchEvent(
            match_id="M042", elapsed=67, type="Goal", detail="Normal Goal",
            player_id=10, player_name="Mbappe", team_id=1, team_name="France",
            captured_at=datetime.utcnow() - timedelta(seconds=45),
        ),
    ])
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    dispatch_pending_events()  # second pass MUST dedup
    assert len(patch_dispatcher) == 1


# ---------------------------------------------------------------------------
# Red card
# ---------------------------------------------------------------------------


def test_red_card_fires_immediately(db, patch_dispatcher):
    s, _ = db
    s.add_all([
        FollowedMatch(endpoint="ep://A", match_id="M042"),
        MatchEvent(
            match_id="M042", elapsed=54, type="Card", detail="Red Card",
            player_id=22, player_name="Pogba", team_id=1, team_name="France",
            captured_at=datetime.utcnow(),  # red cards don't need confirm delay
        ),
    ])
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    assert len(patch_dispatcher) == 1
    assert "Red card" in patch_dispatcher[0]["title"]
    assert "Pogba" in patch_dispatcher[0]["body"]


# ---------------------------------------------------------------------------
# Half-time / full-time
# ---------------------------------------------------------------------------


def test_half_time_fires_when_lms_status_is_HT(db, patch_dispatcher):
    s, _ = db
    lms = s.query(LiveMatchState).filter_by(match_id="M042").one()
    lms.status = "HT"
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042"))
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    assert any("HT" in p["title"] for p in patch_dispatcher)


def test_full_time_fires_for_complete_match(db, patch_dispatcher):
    s, _ = db
    m = s.query(Match).filter_by(id="M042").one()
    m.status = "complete"
    m.home_score, m.away_score = 2, 1
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042"))
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    fts = [p for p in patch_dispatcher if "FT" in p["title"]]
    assert len(fts) == 1
    assert "2-1" in fts[0]["title"]


def test_full_time_suppressed_when_match_interrupted(db, patch_dispatcher):
    """Awarded match (interruption_status='awarded') has Match.status='complete'
    AND a home_score/away_score, but FT push must NOT fire — picks are void
    per industry rule (see settlement_rules.py)."""
    s, _ = db
    m = s.query(Match).filter_by(id="M042").one()
    m.status = "complete"
    m.home_score, m.away_score = 3, 0
    m.interruption_status = "awarded"
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042"))
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    fts = [p for p in patch_dispatcher if "FT" in p["title"]]
    assert fts == []


# ---------------------------------------------------------------------------
# Interruption lifecycle — always-on
# ---------------------------------------------------------------------------


def test_suspended_event_fires_for_followed_match(db, patch_dispatcher):
    s, _ = db
    m = s.query(Match).filter_by(id="M042").one()
    m.interruption_status = "delayed"
    m.interruption_started_at = datetime.utcnow() - timedelta(hours=1)
    m.interruption_reason = "weather (api-football status=INT)"
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042", event_mask=1))  # tiny mask
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    suspends = [p for p in patch_dispatcher if "suspend" in p["title"].lower()]
    assert len(suspends) == 1
    # Always-on bypasses the mask
    assert "ep://A" in suspends[0]["recipients"]


def test_resumed_event_fires_after_prior_suspended(db, patch_dispatcher):
    s, _ = db
    # First: simulate the prior suspended event was logged.
    s.add(NotificationEventLog(
        match_id="M042", event_type="suspended",
        event_key="suspended:M042:2026-06-22T22:00:00",
        recipients=1,
    ))
    # Match is now resumed (interruption cleared).
    m = s.query(Match).filter_by(id="M042").one()
    m.interruption_status = None
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042"))
    s.commit()

    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    resumes = [p for p in patch_dispatcher if "resumed" in p["title"].lower()]
    assert len(resumes) == 1


def test_resumed_does_not_fire_without_prior_suspended(db, patch_dispatcher):
    s, _ = db
    s.add(FollowedMatch(endpoint="ep://A", match_id="M042"))
    s.commit()
    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    assert all("resumed" not in p["title"].lower() for p in patch_dispatcher)


# ---------------------------------------------------------------------------
# No-follower no-op — empty recipients short-circuits send_push
# ---------------------------------------------------------------------------


def test_no_followers_no_pushes_fired(db, patch_dispatcher):
    s, _ = db
    s.add(MatchEvent(
        match_id="M042", elapsed=67, type="Goal", detail="Normal Goal",
        player_id=10, player_name="Mbappe", team_id=1, team_name="France",
        captured_at=datetime.utcnow() - timedelta(seconds=45),
    ))
    s.commit()
    from backend.data.push_dispatch import dispatch_pending_events
    dispatch_pending_events()
    # send_push was called with empty recipients — captured but recipients=[]
    # Verify either nothing dispatched OR dispatched with empty list.
    for p in patch_dispatcher:
        assert p["recipients"] == []
