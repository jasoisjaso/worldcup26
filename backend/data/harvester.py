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
from backend.data import quota_budget as _qb

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}


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


def _quota_from_response(headers) -> tuple[int | None, int | None]:
    """api-football headers we care about:
      x-ratelimit-requests-remaining   daily counter (binds our load)
      x-ratelimit-remaining            per-minute counter (300 cap on Pro)
    Returns (daily_remaining, per_minute_remaining). Either may be None.
    """
    def _safe_int(v):
        if v is None:
            return None
        try:
            return int(v)
        except Exception:
            return None
    return (
        _safe_int(headers.get("x-ratelimit-requests-remaining")),
        _safe_int(headers.get("x-ratelimit-remaining")),
    )


async def _fetch_once(client: httpx.AsyncClient, endpoint: str, params: dict) -> tuple[int, str, int | None, int | None]:
    """Returns (status_code, response_text, daily_remaining, per_minute_remaining)."""
    url = f"{_BASE}{endpoint}"
    r = await client.get(url, params=params, headers=_HEADERS, timeout=30.0)
    daily, per_min = _quota_from_response(r.headers)
    return r.status_code, r.text, daily, per_min


# In-memory daily quota-exhaustion marker. When set, harvester skips until
# the date rolls over (UTC). Avoids burning calls confirming we're out.
_QUOTA_EXHAUSTED_DATE: str | None = None


def _today_utc_iso() -> str:
    return datetime.utcnow().date().isoformat()


def _is_quota_exhausted_body(text: str) -> bool:
    """api-football returns HTTP 200 with `errors.requests` set when the
    daily quota is exhausted. Detect this so we don't mark a quota-blocked
    job as 'done' with no data."""
    try:
        return "request limit for the day" in (text or "")
    except Exception:
        return False


async def run_one_pass() -> dict:
    """One tick: pick the next pending job, fetch, persist.

    Pacing is handled by quota_budget.harvester_can_run() — we refuse to
    run in Phase 1 (backfill's window), pace ourselves in Phase 2 based on
    remaining quota, and burn everything in Phase 3 (final 2 hours before
    reset) down to a 50-call emergency buffer."""
    if not _API_KEY:
        return {"status": "no_api_key"}

    _qb.reset_if_new_day()

    if _qb.quota_exhausted_today():
        return {"status": "skipped", "reason": "daily_quota_exhausted"}

    db = SessionLocal()
    try:
        # Phase / budget gate: don't even enter if the harvester shouldn't run.
        if not _qb.harvester_can_run():
            return {"status": "skipped", "reason": "budget_gated"}

        now = datetime.utcnow()
        # Container restart leaves jobs stuck in `in_progress` forever — recover
        # any older than 10 minutes by flipping them back to pending so they get
        # another shot. Cheap DB-local sweep, no API calls.
        stale = (
            db.query(HarvestJob)
            .filter(HarvestJob.status == "in_progress")
            .filter(HarvestJob.attempted_at < now - timedelta(minutes=10))
            .all()
        )
        for j in stale:
            j.status = "pending"
            j.attempted_at = None
        if stale:
            db.commit()

        # Pick the highest-priority pending job whose schedule has arrived.
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
            return {"status": "idle"}

        # Mark as in-progress so concurrent ticks don't race.
        job.status = "in_progress"
        job.attempted_at = now
        db.commit()

        try:
            params = json.loads(job.params_json)
            async with httpx.AsyncClient(timeout=30.0) as client:
                sc, text, new_remaining, per_minute = await _fetch_once(client, job.endpoint, params)

            # Save the raw response unconditionally — even errors give us
            # diagnostic info for re-runs.
            db.add(HarvestRaw(
                job_id=job.id,
                endpoint=job.endpoint,
                response_json=text,
                status_code=sc,
            ))

            # Quota-exhausted: 200 + error in body. DON'T mark as done — flip
            # back to pending so it retries when quota resets, and stop the
            # harvester for the day.
            if sc == 200 and _is_quota_exhausted_body(text):
                job.status = "pending"
                job.attempted_at = None
                _qb.mark_quota_exhausted()
                db.commit()
                return {
                    "status": "skipped",
                    "reason": "daily_quota_exhausted",
                    "job_id": job.id,
                }

            _qb.update_quota(new_remaining, per_minute)

            if sc == 200:
                job.status = "done"
                job.response_size_bytes = len(text or "")
            else:
                job.status = "error"
                job.error_msg = (text or "")[:200]

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
