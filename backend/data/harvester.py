"""Background harvester for api-football endpoints.

Designed to be the engine that fills our proprietary dataset over time without
ever stealing quota from the live polling path. Runs every few minutes, takes
one pending HarvestJob at a time, calls api-football, persists the raw JSON
into HarvestRaw, marks the job done. Workers refuse to fire when remaining
daily quota dips below LIVE_RESERVE_FLOOR.

Architecture (intentional choices):

- Raw JSON kept forever in HarvestRaw. Schema can change later; we re-process
  raw blobs into normalised tables without re-paying the API cost.
- One job at a time per tick. Backpressure-friendly; avoids spiking the API.
- dedup_key (endpoint + sorted params) prevents re-queueing the same fetch.
- Priority ordering: low number = soon. WC squads start at priority 50,
  player histories at 100, league fixture sweeps at 200, per-fixture
  statistics at 300.

NOTE: This is the foundation only. Seeding the queue with the full priority
list happens via seed_initial_queue() — called once on startup so the queue
self-fills as new content becomes available."""
from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy import and_

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import HarvestJob, HarvestRaw
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# Daily quota guard. api-football Pro plan is 7,500/day. We reserve 1,500 for
# the live poller + prematch prefetch + scoring jobs. Harvester refuses to run
# once we dip below this — set conservatively so we never starve live.
LIVE_RESERVE_FLOOR = 1500


def _dedup_key(endpoint: str, params: dict) -> str:
    """Canonical hash of (endpoint, sorted-params) so duplicate jobs collapse."""
    raw = endpoint + "|" + json.dumps(params, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue(endpoint: str, params: dict, priority: int = 200, scheduled_for: datetime | None = None) -> bool:
    """Queue one fetch. Returns True if added, False if it was already queued
    (dedup) or already completed (we keep done jobs forever for traceability)."""
    key = _dedup_key(endpoint, params)
    db = SessionLocal()
    try:
        existing = db.query(HarvestJob).filter(HarvestJob.dedup_key == key).first()
        if existing:
            return False
        db.add(HarvestJob(
            endpoint=endpoint,
            params_json=json.dumps(params, sort_keys=True),
            priority=priority,
            status="pending",
            scheduled_for=scheduled_for or datetime.utcnow(),
            dedup_key=key,
        ))
        db.commit()
        return True
    finally:
        db.close()


def _quota_remaining_from_response(headers) -> int | None:
    """api-football returns daily call counters in response headers
    `x-ratelimit-requests-remaining` (per minute) and `x-ratelimit-requests-limit`
    (daily). We read the daily one."""
    rem = headers.get("x-ratelimit-requests-remaining")
    if rem is not None:
        try:
            return int(rem)
        except Exception:
            return None
    return None


async def _fetch_once(client: httpx.AsyncClient, endpoint: str, params: dict) -> tuple[int, str, int | None]:
    """Returns (status_code, response_text, quota_remaining_or_None)."""
    url = f"{_BASE}{endpoint}"
    r = await client.get(url, params=params, headers=_HEADERS, timeout=30.0)
    return r.status_code, r.text, _quota_remaining_from_response(r.headers)


async def run_one_pass() -> dict:
    """One tick: pick the next pending job, check quota, fetch, persist.

    Returns a summary dict the scheduler health endpoint can surface. Always
    safe to call when quota is tight; it just returns 'skipped'."""
    if not _API_KEY:
        return {"status": "no_api_key"}

    # Cheapest possible quota check: hit a known light endpoint just for the
    # quota header. We do this ONCE per pass before deciding to run.
    async with httpx.AsyncClient(timeout=15.0) as probe:
        try:
            sc, _, remaining = await _fetch_once(probe, "/status", {})
            if sc != 200 or remaining is None:
                # We can't read the quota reliably — be safe and skip.
                return {"status": "skipped", "reason": "quota_unreadable"}
            if remaining < LIVE_RESERVE_FLOOR:
                return {"status": "skipped", "reason": "below_floor", "remaining": remaining}
        except Exception as exc:
            return {"status": "skipped", "reason": f"probe_failed: {exc}"}

    db = SessionLocal()
    try:
        # Pick the highest-priority pending job whose schedule has arrived.
        now = datetime.utcnow()
        job = (
            db.query(HarvestJob)
            .filter(and_(
                HarvestJob.status == "pending",
                HarvestJob.scheduled_for <= now,
            ))
            .order_by(HarvestJob.priority.asc(), HarvestJob.scheduled_for.asc())
            .first()
        )
        if not job:
            return {"status": "idle", "quota_remaining": remaining}

        # Mark as in-progress so concurrent ticks don't race.
        job.status = "in_progress"
        job.attempted_at = now
        db.commit()

        try:
            params = json.loads(job.params_json)
            async with httpx.AsyncClient(timeout=30.0) as client:
                sc, text, new_remaining = await _fetch_once(client, job.endpoint, params)

            # Save the raw response unconditionally — even errors give us
            # diagnostic info for re-runs.
            db.add(HarvestRaw(
                job_id=job.id,
                endpoint=job.endpoint,
                response_json=text,
                status_code=sc,
            ))

            if sc == 200:
                job.status = "done"
                job.response_size_bytes = len(text or "")
            else:
                job.status = "error"
                job.error_msg = text[:200]

            job.completed_at = datetime.utcnow()
            db.commit()

            return {
                "status": "ran",
                "job_id": job.id,
                "endpoint": job.endpoint,
                "http_status": sc,
                "bytes": job.response_size_bytes,
                "quota_remaining_after": new_remaining,
            }
        except Exception as exc:
            job.status = "error"
            job.error_msg = str(exc)[:200]
            job.completed_at = datetime.utcnow()
            db.commit()
            return {"status": "error", "job_id": job.id, "error": str(exc)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Queue seeders — kept narrow on purpose. WC squads first, expand later.
# ---------------------------------------------------------------------------

def seed_wc_squads() -> dict:
    """One job per WC team — fetch the squad list. ~48 jobs, ~48 calls.

    Each successful response gives us 23-30 player records with player_id, age,
    position, club, jersey number — the canonical PlayerProfile seed plus the
    starting point for /players histories.
    """
    added = 0
    skipped = 0
    for team_code, api_id in TEAM_IDS.items():
        ok = enqueue(
            endpoint="/players/squads",
            params={"team": api_id},
            priority=50,  # highest priority of the harvester jobs
        )
        if ok:
            added += 1
        else:
            skipped += 1
    return {"added": added, "skipped_already_queued": skipped}


def queue_status() -> dict:
    """Snapshot of the queue — surfaces via the admin endpoint."""
    db = SessionLocal()
    try:
        by_status: dict[str, int] = {}
        for s in ["pending", "in_progress", "done", "error", "skipped"]:
            by_status[s] = db.query(HarvestJob).filter(HarvestJob.status == s).count()
        last_done = (
            db.query(HarvestJob)
            .filter(HarvestJob.status == "done")
            .order_by(HarvestJob.completed_at.desc())
            .first()
        )
        return {
            "by_status": by_status,
            "total_raw_blobs": db.query(HarvestRaw).count(),
            "last_completed": {
                "id": last_done.id,
                "endpoint": last_done.endpoint,
                "completed_at": last_done.completed_at.isoformat() if last_done and last_done.completed_at else None,
                "bytes": last_done.response_size_bytes,
            } if last_done else None,
        }
    finally:
        db.close()
