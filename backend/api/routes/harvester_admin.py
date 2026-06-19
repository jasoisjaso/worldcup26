"""Admin endpoints for the background data harvester.

Internal-only — never linked from the public UI. Used to inspect the queue,
manually seed it, and force a tick when needed.
"""
from fastapi import APIRouter

from backend.data.harvester import (
    queue_status,
    run_one_pass,
    seed_wc_squads,
)
from backend.data.harvester_seed import (
    seed_full_stack,
    seed_league_fixtures,
    seed_all_leagues,
)
from backend.data import quota_budget as _qb

router = APIRouter()


@router.get("/status")
async def get_status():
    return queue_status()


@router.get("/dashboard")
async def get_dashboard():
    """Pipeline health: queue depth + processor throughput + quota budget."""
    from backend.db.session import SessionLocal
    from backend.db.models import HarvestJob, HarvestRaw, HarvestErrorLog, PlayerProfile, FixtureArchive, PlayerHistory

    db = SessionLocal()
    try:
        by_status: dict[str, int] = {}
        for s in ["pending", "in_progress", "done", "error"]:
            by_status[s] = db.query(HarvestJob).filter(HarvestJob.status == s).count()

        raw_total = db.query(HarvestRaw).count()
        raw_processed = db.query(HarvestRaw).filter(HarvestRaw.processed == True).count()  # noqa: E712
        raw_unprocessed = raw_total - raw_processed

        errors_24h = db.query(HarvestErrorLog).count()

        return {
            "queue": by_status,
            "raw_blobs": {"total": raw_total, "processed": raw_processed, "unprocessed": raw_unprocessed},
            "tables": {
                "player_profiles": db.query(PlayerProfile).count(),
                "fixture_archives": db.query(FixtureArchive).count(),
                "player_history": db.query(PlayerHistory).count(),
            },
            "errors_24h": errors_24h,
            "quota_budget": _qb.budget_summary(),
        }
    finally:
        db.close()


@router.post("/seed/wc-squads")
async def post_seed_wc_squads():
    """One job per WC team — fetch the current squad. ~48 jobs queued."""
    return seed_wc_squads()


@router.post("/seed/full")
async def post_seed_full():
    """WC player stats + EPL/Bundesliga fixtures. Dedup-safe."""
    return seed_full_stack()


@router.post("/seed/leagues")
async def post_seed_leagues():
    """League fixtures for EPL + Bundesliga only."""
    return seed_league_fixtures()


@router.post("/seed/all-leagues")
async def post_seed_all_leagues():
    """All 9 leagues × 2 seasons. Heavy queue — ~4,600 fixture jobs."""
    return seed_all_leagues()


@router.post("/run-one")
async def post_run_one():
    """Force a single tick of the harvester (useful for manual backfill)."""
    return await run_one_pass()
