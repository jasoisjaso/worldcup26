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

router = APIRouter()


@router.get("/status")
async def get_status():
    return queue_status()


@router.post("/seed/wc-squads")
async def post_seed_wc_squads():
    """One job per WC team — fetch the current squad. ~48 jobs queued."""
    return seed_wc_squads()


@router.post("/run-one")
async def post_run_one():
    """Force a single tick of the harvester (useful for manual backfill)."""
    return await run_one_pass()
