"""
Push notification subscription endpoint.
Stores browser push subscriptions so the value-pick logger can send alerts.

POST /push/subscribe
POST /push/unsubscribe
"""
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()

# In-memory store (resets on deploy — acceptable for tournament duration)
_subscriptions: list[dict] = []


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict


@router.post("/subscribe")
async def subscribe(sub: PushSubscription):
    """Store a push subscription."""
    entry = sub.model_dump()
    # Deduplicate
    existing = [s for s in _subscriptions if s["endpoint"] == entry["endpoint"]]
    for e in existing:
        _subscriptions.remove(e)
    _subscriptions.append(entry)
    return {"status": "ok", "subscribers": len(_subscriptions)}


@router.post("/unsubscribe")
async def unsubscribe(sub: PushSubscription):
    """Remove a push subscription."""
    global _subscriptions
    _subscriptions = [s for s in _subscriptions if s["endpoint"] != sub.endpoint]
    return {"status": "ok", "subscribers": len(_subscriptions)}


def get_subscriptions() -> list[dict]:
    """Return all stored subscriptions for sending push notifications."""
    return list(_subscriptions)
