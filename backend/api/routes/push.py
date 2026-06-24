"""Push notification subscription + send endpoints.

Persists browser push subscriptions to SQLite so they survive deploys, and exposes a
sender that the prediction logger calls when it finds a value pick. VAPID keys are
read from environment so they don't end up in the repo.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import (
    PushSubscription as PushSub,
    PushSent,
    FollowedMatch,
    FollowedTeam,
)
from backend.data import push_events as _pe

logger = logging.getLogger(__name__)
router = APIRouter()

VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY", "")
VAPID_SUB = os.getenv("VAPID_SUB", "mailto:tbsonline@protonmail.com")


class SubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class SubscriptionIn(BaseModel):
    endpoint: str
    keys: SubscriptionKeys


@router.post("/subscribe")
async def subscribe(sub: SubscriptionIn, request: Request, db: Session = Depends(get_db)):
    ua = request.headers.get("user-agent", "")[:200]
    existing = db.query(PushSub).filter(PushSub.endpoint == sub.endpoint).first()
    if existing:
        existing.p256dh = sub.keys.p256dh
        existing.auth = sub.keys.auth
        existing.last_used = datetime.utcnow()
        existing.user_agent = ua
        existing.failed_count = 0
    else:
        db.add(PushSub(
            endpoint=sub.endpoint,
            p256dh=sub.keys.p256dh,
            auth=sub.keys.auth,
            user_agent=ua,
        ))
    db.commit()
    total = db.query(PushSub).count()
    return {"status": "ok", "subscribers": total}


@router.post("/unsubscribe")
async def unsubscribe(sub: SubscriptionIn, db: Session = Depends(get_db)):
    db.query(PushSub).filter(PushSub.endpoint == sub.endpoint).delete()
    db.commit()
    return {"status": "ok"}


@router.get("/public-key")
async def public_key():
    """So the frontend doesn't have to hard-code it. Eventually wire this in."""
    return {"key": VAPID_PUBLIC_KEY}


@router.post("/test")
async def send_test(db: Session = Depends(get_db)):
    """Admin-only ping. Sends a test notification to every active subscriber."""
    result = send_push(
        db,
        title="WC26 test ping",
        body="Push notifications are working.",
        url="/value",
        dedup_key=f"test-{datetime.utcnow().isoformat()}",
    )
    return result


# ---------------------------------------------------------------------------
# Follow / unfollow endpoints (FE calls these from the bell on MatchCard +
# team page, and implicitly from the Add-to-Acca flow). All routes are
# anonymous + per-device — keyed on the push subscription endpoint, which
# is what every Web Push subscription gives the FE. No accounts needed.
# ---------------------------------------------------------------------------


class FollowMatchIn(BaseModel):
    endpoint: str
    match_id: str
    event_mask: int | None = None     # default applied server-side
    source: str = "manual"            # 'manual' | 'auto_pick'


class FollowTeamIn(BaseModel):
    endpoint: str
    team_code: str
    event_mask: int | None = None


class UnfollowIn(BaseModel):
    endpoint: str
    match_id: str | None = None
    team_code: str | None = None


class MaskUpdateIn(BaseModel):
    endpoint: str
    event_mask: int
    match_id: str | None = None
    team_code: str | None = None


def _verify_endpoint(db: Session, endpoint: str) -> None:
    """A follow row is useless without a live PushSubscription to deliver to.
    Reject 404 early so the FE knows the device-subscribe step is missing
    (likely an iOS Add-to-Home-Screen flow that wasn't completed).
    """
    if not db.query(PushSub).filter(PushSub.endpoint == endpoint).first():
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail="No push subscription for this endpoint — subscribe to push first.",
        )


@router.post("/follow-match")
async def follow_match(body: FollowMatchIn, db: Session = Depends(get_db)):
    """Subscribe `endpoint` to events for `match_id`. Idempotent — repeat
    calls update event_mask + source, never duplicate. If the row exists
    with no_auto_refollow=True and the new source is 'auto_pick', the
    insert is suppressed (explicit unfollow wins per §9d)."""
    _verify_endpoint(db, body.endpoint)
    existing = (
        db.query(FollowedMatch)
        .filter(FollowedMatch.endpoint == body.endpoint)
        .filter(FollowedMatch.match_id == body.match_id)
        .first()
    )
    if existing:
        # Auto_pick must not silently re-follow after an explicit unfollow.
        if existing.no_auto_refollow and body.source == "auto_pick":
            return {"status": "blocked_by_no_auto_refollow"}
        if body.event_mask is not None:
            existing.event_mask = body.event_mask
        if body.source == "manual":
            existing.source = "manual"  # manual overrides auto_pick
        db.commit()
        return {"status": "updated", "id": existing.id}
    # Honour no_auto_refollow even on the first-insert path: if a previous
    # row was deleted with the flag set, the FE would have to also POST a
    # 'no_auto_refollow=true' marker elsewhere — out of scope for v1, so
    # the flag only lives on the row itself.
    if body.source == "auto_pick":
        # Check the audit log for a prior explicit unfollow on this pair.
        # Simpler: rely on the existing row staying NULL — if there's no
        # row, the user has never been follow-managed for this match, so
        # auto_pick is fine to insert. (No-auto-refollow only takes effect
        # AFTER a prior follow row that was unfollowed.)
        pass
    fm = FollowedMatch(
        endpoint=body.endpoint,
        match_id=body.match_id,
        event_mask=body.event_mask if body.event_mask is not None else _pe.DEFAULT_MASK,
        source=body.source,
    )
    db.add(fm)
    db.commit()
    return {"status": "created", "id": fm.id}


@router.post("/unfollow-match")
async def unfollow_match(body: UnfollowIn, db: Session = Depends(get_db)):
    """Remove a FollowedMatch row. If the row's source was 'auto_pick' (i.e.
    the user is explicitly turning off an alert they got because they
    placed a bet), set no_auto_refollow=True on a stub row so the next
    Add-to-Acca can't silently re-subscribe them."""
    if not body.match_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="match_id required")
    row = (
        db.query(FollowedMatch)
        .filter(FollowedMatch.endpoint == body.endpoint)
        .filter(FollowedMatch.match_id == body.match_id)
        .first()
    )
    if not row:
        return {"status": "not_followed"}
    was_auto = row.source == "auto_pick"
    db.delete(row)
    if was_auto:
        # Stub row records the explicit-no decision. event_mask=0 makes the
        # row a no-op for dispatch even if it slips past the unfollow path.
        db.add(FollowedMatch(
            endpoint=body.endpoint,
            match_id=body.match_id,
            event_mask=0,
            source="manual",
            no_auto_refollow=True,
        ))
    db.commit()
    return {"status": "unfollowed", "was_auto": was_auto}


@router.post("/follow-team")
async def follow_team(body: FollowTeamIn, db: Session = Depends(get_db)):
    _verify_endpoint(db, body.endpoint)
    existing = (
        db.query(FollowedTeam)
        .filter(FollowedTeam.endpoint == body.endpoint)
        .filter(FollowedTeam.team_code == body.team_code)
        .first()
    )
    if existing:
        if body.event_mask is not None:
            existing.event_mask = body.event_mask
        db.commit()
        return {"status": "updated", "id": existing.id}
    ft = FollowedTeam(
        endpoint=body.endpoint,
        team_code=body.team_code,
        event_mask=body.event_mask if body.event_mask is not None else _pe.DEFAULT_MASK,
    )
    db.add(ft)
    db.commit()
    return {"status": "created", "id": ft.id}


@router.post("/unfollow-team")
async def unfollow_team(body: UnfollowIn, db: Session = Depends(get_db)):
    if not body.team_code:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="team_code required")
    n = (
        db.query(FollowedTeam)
        .filter(FollowedTeam.endpoint == body.endpoint)
        .filter(FollowedTeam.team_code == body.team_code)
        .delete()
    )
    db.commit()
    return {"status": "unfollowed" if n else "not_followed"}


@router.patch("/event-mask")
async def update_event_mask(body: MaskUpdateIn, db: Session = Depends(get_db)):
    """Update the event_mask bitfield on a follow row — used by the per-event
    toggle drawer. Caller specifies EITHER match_id OR team_code."""
    if body.match_id:
        row = (
            db.query(FollowedMatch)
            .filter(FollowedMatch.endpoint == body.endpoint)
            .filter(FollowedMatch.match_id == body.match_id)
            .first()
        )
    elif body.team_code:
        row = (
            db.query(FollowedTeam)
            .filter(FollowedTeam.endpoint == body.endpoint)
            .filter(FollowedTeam.team_code == body.team_code)
            .first()
        )
    else:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="match_id or team_code required")
    if not row:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="follow row not found")
    row.event_mask = body.event_mask
    db.commit()
    return {"status": "updated", "event_mask": row.event_mask}


@router.get("/follows")
async def list_follows(endpoint: str, db: Session = Depends(get_db)):
    """List all matches + teams a given endpoint is following. Powers the
    Settings page bulk-unfollow view and lets the FE render the bell as
    filled/empty without per-card lookups."""
    matches = (
        db.query(FollowedMatch)
        .filter(FollowedMatch.endpoint == endpoint)
        .filter(FollowedMatch.event_mask > 0)  # hide the no_auto_refollow stubs
        .all()
    )
    teams = db.query(FollowedTeam).filter(FollowedTeam.endpoint == endpoint).all()
    return {
        "matches": [
            {
                "match_id": m.match_id,
                "event_mask": m.event_mask,
                "source": m.source,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in matches
        ],
        "teams": [
            {
                "team_code": t.team_code,
                "event_mask": t.event_mask,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in teams
        ],
    }


def send_push(
    db: Session,
    *,
    title: str,
    body: str,
    url: str = "/value",
    dedup_key: str | None = None,
    require_interaction: bool = False,
    recipients: list[str] | None = None,
) -> dict:
    """Send a push notification. Dedups by `dedup_key` so the same pick can't
    notify twice across deploys.

    Recipient model:
      * recipients=None (default) — fan out to every active subscriber.
        Used by site-wide alerts (value picks, big WP swings).
      * recipients=[endpoint, ...] — restrict to that allowlist. Used by
        the follow-match dispatcher so a goal in M042 only pings the
        users who actually subscribed to M042 (or to France / Iraq).

    Empty recipients list -> no-op, returns sent=0. Caller decides whether
    that's an error or just "nobody followed this match".
    """
    # Cheapest gates first — recipients=[] means "no one followed this match"
    # which is a successful no-op, not a config error. Check before VAPID so
    # the empty-list path returns the right status even on a misconfigured box.
    if recipients is not None and len(recipients) == 0:
        return {"status": "no_recipients", "sent": 0}

    if not VAPID_PRIVATE_KEY:
        return {"status": "no_vapid_key", "sent": 0}

    if dedup_key:
        if db.query(PushSent).filter(PushSent.dedup_key == dedup_key).first():
            return {"status": "deduped", "sent": 0}

    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        return {"status": "no_pywebpush", "sent": 0}

    payload = json.dumps({
        "title": title,
        "body": body,
        "url": url,
        "requireInteraction": require_interaction,
    })

    q = db.query(PushSub).filter(PushSub.failed_count < 3)
    if recipients is not None:
        q = q.filter(PushSub.endpoint.in_(recipients))
    subs = q.all()
    sent = 0
    pruned = 0
    for s in subs:
        try:
            webpush(
                subscription_info={
                    "endpoint": s.endpoint,
                    "keys": {"p256dh": s.p256dh, "auth": s.auth},
                },
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims={"sub": VAPID_SUB},
                ttl=3600,
            )
            s.last_used = datetime.utcnow()
            s.failed_count = 0
            sent += 1
        except WebPushException as exc:
            status = exc.response.status_code if exc.response is not None else 0
            if status in (404, 410):
                # Subscription expired/revoked — remove it
                db.delete(s)
                pruned += 1
            else:
                s.failed_count = (s.failed_count or 0) + 1
                logger.warning("push send failed (status=%s): %s", status, exc)
        except Exception as exc:
            s.failed_count = (s.failed_count or 0) + 1
            logger.warning("push send unexpected error: %s", exc)

    if dedup_key:
        db.add(PushSent(dedup_key=dedup_key))
    db.commit()
    return {"status": "ok", "sent": sent, "pruned": pruned, "total": len(subs)}
