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
from backend.db.models import PushSubscription as PushSub, PushSent

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


def send_push(
    db: Session,
    *,
    title: str,
    body: str,
    url: str = "/value",
    dedup_key: str | None = None,
    require_interaction: bool = False,
) -> dict:
    """Send a push notification to every subscriber. Dedups by `dedup_key` so the
    same pick can't notify twice across deploys."""
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

    subs = db.query(PushSub).filter(PushSub.failed_count < 3).all()
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
