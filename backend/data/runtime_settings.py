"""Runtime-mutable settings persisted in the SettingsKV table.

These are the operator toggles the admin UI flips without a redeploy. Kept
tiny and explicit: every key has its own typed getter so the admin layer can't
accidentally write the wrong shape. Falls back to env vars when the row is
missing so a fresh DB still respects the deploy-time defaults.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

from sqlalchemy.exc import OperationalError

from backend.db.models import SettingsKV
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

# Keys we use. Centralised so a typo can't drift two readers apart.
KEY_HARVEST_PAUSED = "harvest_paused"   # "1" → all api-football consumers stop


def _get_raw(key: str) -> str | None:
    db = SessionLocal()
    try:
        row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
        return row.value if row else None
    except OperationalError:
        # Table not migrated yet (fresh DB before init_db runs). Treat as unset.
        return None
    finally:
        db.close()


def _set_raw(key: str, value: str | None) -> None:
    db = SessionLocal()
    try:
        row = db.query(SettingsKV).filter(SettingsKV.key == key).first()
        if row is None:
            db.add(SettingsKV(key=key, value=value, updated_at=datetime.utcnow()))
        else:
            row.value = value
            row.updated_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def harvest_paused() -> bool:
    """True when the admin has flipped the pause toggle. Falls back to env
    (WC26_HARVEST=0 → paused) so deploy-time intent still works on a fresh DB."""
    v = _get_raw(KEY_HARVEST_PAUSED)
    if v is not None:
        return v in ("1", "true", "True", "yes")
    # Env fallback: WC26_HARVEST=0 means paused (matches quota_budget semantics).
    return os.getenv("WC26_HARVEST", "1") in ("0", "false", "False", "no")


def set_harvest_paused(paused: bool) -> None:
    _set_raw(KEY_HARVEST_PAUSED, "1" if paused else "0")


def snapshot() -> dict:
    """Read every settings row for the admin overview."""
    db = SessionLocal()
    try:
        rows = db.query(SettingsKV).all()
        return {
            r.key: {
                "value": r.value,
                "updated_at": r.updated_at.isoformat() if r.updated_at else None,
            }
            for r in rows
        }
    except OperationalError:
        return {}
    finally:
        db.close()
