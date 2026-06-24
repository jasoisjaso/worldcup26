"""Schema + bitmask pinning for the follow-match notification layer.

Locks down the bit positions (wire-stable), the DEFAULT_MASK value
(saved subscriptions would silently get the wrong defaults if it
drifted), and the new ORM models can round-trip.
"""
from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.data import push_events as pe
from backend.db.models import (
    Base,
    FollowedMatch,
    FollowedTeam,
    NotificationEventLog,
    PushSubscription,
)


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    s = Session()
    yield s
    s.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Bit layout — wire contract with the FE. Renumbering breaks every saved sub.
# ---------------------------------------------------------------------------


def test_bit_positions_are_stable():
    # If any of these assertions trip, an FE bitmask saved before the change
    # will silently mean a different event after deploy. NEVER renumber —
    # append new event types at the next free bit instead.
    assert pe.KICKOFF          == 1
    assert pe.GOAL             == 2
    assert pe.RED_CARD         == 4
    assert pe.HALF_TIME        == 8
    assert pe.FULL_TIME        == 16
    assert pe.LINEUP_PUBLISHED == 32
    assert pe.VAR_REVIEW       == 64
    assert pe.PENALTY          == 128


def test_default_mask_value():
    # Default-on = everything except lineup. User decision 2026-06-23
    # bumped VAR + penalty into the default set (override of FotMob's
    # default-off pattern). 1+2+4+8+16+64+128 = 223.
    assert pe.DEFAULT_MASK == 223
    assert not pe.mask_enabled(pe.DEFAULT_MASK, pe.LINEUP_PUBLISHED)
    for bit in (pe.KICKOFF, pe.GOAL, pe.RED_CARD, pe.HALF_TIME,
                pe.FULL_TIME, pe.VAR_REVIEW, pe.PENALTY):
        assert pe.mask_enabled(pe.DEFAULT_MASK, bit)


def test_always_on_events_not_in_mask():
    # Suspended + resumed bypass the mask — users can't silence them.
    # The dispatcher checks ALWAYS_ON_EVENTS BEFORE consulting the mask.
    assert "suspended" in pe.ALWAYS_ON_EVENTS
    assert "resumed" in pe.ALWAYS_ON_EVENTS
    # And these strings don't map to a bit (caller checks ALWAYS_ON first).
    assert pe.event_type_to_bit("suspended") is None
    assert pe.event_type_to_bit("resumed") is None


def test_event_type_to_bit_round_trip():
    # Every name the dispatcher uses must resolve to a bit.
    expected = {
        "kickoff": pe.KICKOFF, "goal": pe.GOAL, "red_card": pe.RED_CARD,
        "half_time": pe.HALF_TIME, "full_time": pe.FULL_TIME,
        "lineup_published": pe.LINEUP_PUBLISHED, "var_review": pe.VAR_REVIEW,
        "penalty": pe.PENALTY,
    }
    for name, bit in expected.items():
        assert pe.event_type_to_bit(name) == bit


# ---------------------------------------------------------------------------
# Model round-trips
# ---------------------------------------------------------------------------


def test_followed_match_defaults(db):
    f = FollowedMatch(endpoint="ep://1", match_id="M042")
    db.add(f)
    db.commit()
    db.expire_all()
    row = db.query(FollowedMatch).one()
    assert row.event_mask == pe.DEFAULT_MASK
    assert row.source == "manual"
    assert row.no_auto_refollow is False


def test_followed_match_auto_pick_source(db):
    f = FollowedMatch(endpoint="ep://1", match_id="M042", source="auto_pick")
    db.add(f)
    db.commit()
    db.expire_all()
    assert db.query(FollowedMatch).one().source == "auto_pick"


def test_followed_team_defaults(db):
    f = FollowedTeam(endpoint="ep://2", team_code="fr")
    db.add(f)
    db.commit()
    db.expire_all()
    assert db.query(FollowedTeam).one().event_mask == pe.DEFAULT_MASK


def test_event_log_dedup_via_unique_constraint(db):
    db.add(NotificationEventLog(
        match_id="M042", event_type="goal",
        event_key="goal:M042:67:fr", recipients=3,
    ))
    db.commit()
    # Re-inserting the same event_key must fail — that's our dedup gate.
    db.add(NotificationEventLog(
        match_id="M042", event_type="goal",
        event_key="goal:M042:67:fr", recipients=3,
    ))
    with pytest.raises(Exception):
        db.commit()
    db.rollback()


# ---------------------------------------------------------------------------
# send_push recipients allowlist — the new filter
# ---------------------------------------------------------------------------


def test_send_push_recipients_empty_is_noop(db):
    from backend.api.routes.push import send_push
    # No VAPID key in this env, but the recipients=[] check fires BEFORE
    # the VAPID gate so we still get the right short-circuit.
    res = send_push(
        db, title="t", body="b", url="/", recipients=[],
    )
    assert res["status"] == "no_recipients"
    assert res["sent"] == 0


def test_send_push_no_vapid_key_short_circuits(db, monkeypatch):
    from backend.api.routes import push as push_mod
    monkeypatch.setattr(push_mod, "VAPID_PRIVATE_KEY", "")
    res = push_mod.send_push(db, title="t", body="b")
    assert res["status"] == "no_vapid_key"


def test_send_push_recipients_filter_query(db, monkeypatch):
    """When recipients is set AND VAPID is configured, the query must filter
    PushSubscription rows by endpoint. We assert the query, not the actual
    webpush call (which would need real VAPID keys + network).
    """
    from backend.api.routes import push as push_mod
    db.add_all([
        PushSubscription(endpoint="ep://A", p256dh="x", auth="y"),
        PushSubscription(endpoint="ep://B", p256dh="x", auth="y"),
        PushSubscription(endpoint="ep://C", p256dh="x", auth="y"),
    ])
    db.commit()

    monkeypatch.setattr(push_mod, "VAPID_PRIVATE_KEY", "fake-key-for-test")
    captured = []

    def fake_webpush(*args, **kwargs):
        captured.append(kwargs["subscription_info"]["endpoint"])

    # Stub the pywebpush import that send_push does lazily.
    import sys as _sys
    fake_module = type(_sys)("pywebpush")
    fake_module.webpush = fake_webpush
    fake_module.WebPushException = type("WebPushException", (Exception,), {})
    monkeypatch.setitem(_sys.modules, "pywebpush", fake_module)

    res = push_mod.send_push(
        db, title="goal!", body="France 1-0", url="/match/M042",
        recipients=["ep://A", "ep://C"],
    )
    assert res["sent"] == 2
    assert set(captured) == {"ep://A", "ep://C"}, f"got {captured}"


def test_send_push_no_recipients_still_fans_out(db, monkeypatch):
    """When recipients=None (the original default), behaviour is unchanged —
    every active subscriber gets the push. This is the back-compat test."""
    from backend.api.routes import push as push_mod
    db.add_all([
        PushSubscription(endpoint="ep://A", p256dh="x", auth="y"),
        PushSubscription(endpoint="ep://B", p256dh="x", auth="y"),
    ])
    db.commit()

    monkeypatch.setattr(push_mod, "VAPID_PRIVATE_KEY", "fake-key-for-test")
    captured = []

    def fake_webpush(*args, **kwargs):
        captured.append(kwargs["subscription_info"]["endpoint"])

    import sys as _sys
    fake_module = type(_sys)("pywebpush")
    fake_module.webpush = fake_webpush
    fake_module.WebPushException = type("WebPushException", (Exception,), {})
    monkeypatch.setitem(_sys.modules, "pywebpush", fake_module)

    res = push_mod.send_push(db, title="t", body="b")  # recipients omitted
    assert res["sent"] == 2
    assert set(captured) == {"ep://A", "ep://B"}
