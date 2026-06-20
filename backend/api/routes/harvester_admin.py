"""Admin endpoints for the background data harvester.

Internal-only — never linked from the public UI. Every route is gated by the
WC26_ADMIN_TOKEN bearer header (see backend.api.admin_auth). The dashboard
front-end at /admin in the Next.js app calls these.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Query

from backend.api.admin_auth import AdminGate
from backend.data import feed_health, quota_budget as _qb, runtime_settings as _rs
from backend.data.harvester import (
    queue_status,
    run_one_pass,
    seed_wc_squads,
)
from backend.data.harvester_seed import (
    seed_all_leagues,
    seed_full_stack,
    seed_league_fixtures,
)

router = APIRouter(dependencies=[AdminGate])


# ---------------------------------------------------------------------------
# Health + dashboard payloads
# ---------------------------------------------------------------------------


@router.get("/status")
async def get_status() -> dict:
    """Lightweight queue snapshot — same shape as before for backwards compat."""
    return queue_status()


@router.get("/dashboard")
async def get_dashboard() -> dict:
    """Pipeline health: queue depth + processor throughput + quota budget.

    Kept for the original JSON-consumer scripts. The new admin UI uses
    /overview which returns everything in one shot.
    """
    from backend.db.models import (
        FixtureArchive,
        HarvestErrorLog,
        HarvestJob,
        HarvestRaw,
        PlayerHistory,
        PlayerProfile,
    )
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        by_status: dict[str, int] = {}
        for s in ["pending", "in_progress", "done", "error"]:
            by_status[s] = db.query(HarvestJob).filter(HarvestJob.status == s).count()

        raw_total = db.query(HarvestRaw).count()
        raw_processed = db.query(HarvestRaw).filter(HarvestRaw.processed == True).count()  # noqa: E712
        raw_unprocessed = raw_total - raw_processed

        errors_total = db.query(HarvestErrorLog).count()

        return {
            "queue": by_status,
            "raw_blobs": {"total": raw_total, "processed": raw_processed, "unprocessed": raw_unprocessed},
            "tables": {
                "player_profiles": db.query(PlayerProfile).count(),
                "fixture_archives": db.query(FixtureArchive).count(),
                "player_history": db.query(PlayerHistory).count(),
            },
            "errors_total": errors_total,
            "quota_budget": _qb.budget_summary(),
        }
    finally:
        db.close()


@router.get("/overview")
async def get_overview() -> dict:
    """Single payload the admin UI fetches on a 30s poll.

    Bundles queue + raw blobs + table sizes + quota budget + feed health +
    cache state + last 5 errors + runtime settings. One round-trip keeps the
    dashboard responsive and the internal API surface small.
    """
    from backend.db.models import (
        FixtureArchive,
        HarvestErrorLog,
        HarvestJob,
        HarvestRaw,
        PlayerHistory,
        PlayerProfile,
        PlayerTournamentStats,
    )
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        by_status: dict[str, int] = {}
        for s in ["pending", "in_progress", "done", "error"]:
            by_status[s] = db.query(HarvestJob).filter(HarvestJob.status == s).count()

        raw_total = db.query(HarvestRaw).count()
        raw_processed = db.query(HarvestRaw).filter(HarvestRaw.processed == True).count()  # noqa: E712

        # Throughput: jobs completed in the last 24h. Cheap query — completed_at is implicitly
        # indexed via the primary key scan but the daily volume is small enough.
        since = datetime.utcnow() - timedelta(hours=24)
        completed_24h = (
            db.query(HarvestJob)
            .filter(HarvestJob.completed_at >= since)
            .filter(HarvestJob.status == "done")
            .count()
        )
        errors_24h = (
            db.query(HarvestErrorLog)
            .filter(HarvestErrorLog.logged_at >= since)
            .count()
        )

        last_done = (
            db.query(HarvestJob)
            .filter(HarvestJob.status == "done")
            .order_by(HarvestJob.completed_at.desc())
            .first()
        )
        last_error = (
            db.query(HarvestErrorLog)
            .order_by(HarvestErrorLog.logged_at.desc())
            .first()
        )

        recent_errors = (
            db.query(HarvestErrorLog)
            .order_by(HarvestErrorLog.logged_at.desc())
            .limit(5)
            .all()
        )

        return {
            "queue": by_status,
            "raw_blobs": {
                "total": raw_total,
                "processed": raw_processed,
                "unprocessed": raw_total - raw_processed,
            },
            "tables": {
                "player_profiles": db.query(PlayerProfile).count(),
                "player_history": db.query(PlayerHistory).count(),
                "player_tournament_stats": db.query(PlayerTournamentStats).count(),
                "fixture_archives": db.query(FixtureArchive).count(),
            },
            "throughput_24h": {
                "completed": completed_24h,
                "errors": errors_24h,
            },
            "last_completed": {
                "id": last_done.id,
                "endpoint": last_done.endpoint,
                "completed_at": last_done.completed_at.isoformat() if last_done and last_done.completed_at else None,
                "bytes": last_done.response_size_bytes,
            } if last_done else None,
            "last_error": {
                "id": last_error.id,
                "endpoint": last_error.endpoint,
                "error_type": last_error.error_type,
                "error_msg": last_error.error_msg,
                "logged_at": last_error.logged_at.isoformat() if last_error.logged_at else None,
            } if last_error else None,
            "recent_errors": [
                {
                    "id": e.id,
                    "endpoint": e.endpoint,
                    "error_type": e.error_type,
                    "error_msg": e.error_msg,
                    "logged_at": e.logged_at.isoformat() if e.logged_at else None,
                }
                for e in recent_errors
            ],
            "quota_budget": _qb.budget_summary(),
            "feeds": feed_health.snapshot(),
            "caches": _cache_state(),
            "settings": _rs.snapshot(),
            "build": {
                "commit": os.getenv("GIT_COMMIT", "unknown"),
            },
        }
    finally:
        db.close()


@router.get("/recent-jobs")
async def get_recent_jobs(
    status: Optional[str] = Query(default=None, description="pending / in_progress / done / error"),
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """Tail of HarvestJob, newest first. Used for the queue inspector."""
    from backend.db.models import HarvestJob
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        q = db.query(HarvestJob)
        if status:
            q = q.filter(HarvestJob.status == status)
        rows = (
            q.order_by(HarvestJob.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "jobs": [
                {
                    "id": j.id,
                    "endpoint": j.endpoint,
                    "params": _try_json(j.params_json),
                    "priority": j.priority,
                    "status": j.status,
                    "attempted_at": j.attempted_at.isoformat() if j.attempted_at else None,
                    "completed_at": j.completed_at.isoformat() if j.completed_at else None,
                    "response_size_bytes": j.response_size_bytes,
                    "error_msg": (j.error_msg or "")[:200],
                }
                for j in rows
            ],
        }
    finally:
        db.close()


@router.get("/recent-errors")
async def get_recent_errors(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    from backend.db.models import HarvestErrorLog
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        rows = (
            db.query(HarvestErrorLog)
            .order_by(HarvestErrorLog.id.desc())
            .limit(limit)
            .all()
        )
        return {
            "count": len(rows),
            "errors": [
                {
                    "id": e.id,
                    "job_id": e.job_id,
                    "endpoint": e.endpoint,
                    "error_type": e.error_type,
                    "error_msg": e.error_msg,
                    "logged_at": e.logged_at.isoformat() if e.logged_at else None,
                }
                for e in rows
            ],
        }
    finally:
        db.close()


@router.get("/caches")
async def get_caches() -> dict:
    """Disk-cache state for odds + tournament. Helps spot stale/missing caches."""
    return _cache_state()


# ---------------------------------------------------------------------------
# Manual actions — seed, run, pause
# ---------------------------------------------------------------------------


@router.post("/seed/wc-squads")
async def post_seed_wc_squads() -> dict:
    """One job per WC team — fetch the current squad. ~48 jobs queued."""
    return seed_wc_squads()


@router.post("/seed/full")
async def post_seed_full() -> dict:
    """WC player stats + EPL/Bundesliga fixtures. Dedup-safe."""
    return seed_full_stack()


@router.post("/seed/leagues")
async def post_seed_leagues() -> dict:
    """League fixtures for EPL + Bundesliga only."""
    return seed_league_fixtures()


@router.post("/seed/all-leagues")
async def post_seed_all_leagues() -> dict:
    """All 9 leagues × 2 seasons. Heavy queue — ~4,600 fixture jobs."""
    return seed_all_leagues()


@router.post("/run-one")
async def post_run_one() -> dict:
    """Force a single tick of the harvester (useful for manual backfill)."""
    return await run_one_pass()


@router.post("/pause")
async def post_pause() -> dict:
    """Pause every api-football harvester consumer until /resume is called.

    The live poller (scores/events) is intentionally NOT paused — the UI still
    needs live data during a match. This freezes the slow background fillers,
    which are where the bulk of the daily quota actually goes.
    """
    _rs.set_harvest_paused(True)
    return {"paused": True, "harvester_enabled": _qb.harvester_enabled()}


@router.post("/resume")
async def post_resume() -> dict:
    _rs.set_harvest_paused(False)
    return {"paused": False, "harvester_enabled": _qb.harvester_enabled()}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _try_json(s: Optional[str]) -> object:
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _cache_state() -> dict:
    """Inspect the on-disk caches (odds + tournament) without importing the
    fetchers — those would trigger module-level side effects we don't want for
    a read-only probe."""
    state_dir = os.environ.get("WC26_STATE_DIR", "/app/data")
    files = {
        "odds_cache": os.path.join(state_dir, "odds_cache.json"),
        "tournament_cache": os.path.join(state_dir, "tournament_cache.json"),
        "quota_state": os.path.join(state_dir, ".wc26_quota_state.json"),
    }
    out: dict[str, dict] = {}
    now = datetime.utcnow().timestamp()
    for name, path in files.items():
        try:
            st = os.stat(path)
            out[name] = {
                "path": path,
                "exists": True,
                "size_bytes": st.st_size,
                "age_seconds": int(now - st.st_mtime),
                "modified_at": datetime.utcfromtimestamp(st.st_mtime).isoformat() + "Z",
            }
        except FileNotFoundError:
            out[name] = {"path": path, "exists": False}
        except Exception as exc:
            out[name] = {"path": path, "exists": False, "error": str(exc)}
    return out
