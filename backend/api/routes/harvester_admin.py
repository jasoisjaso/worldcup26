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
from sqlalchemy import func

from backend.api.admin_auth import AdminGate
from backend.data import feed_health, quota_budget as _qb, runtime_settings as _rs
from backend.data.fetchers.injuries import TEAM_IDS as _WC_TEAM_IDS
from backend.data.fetchers.sharp_odds import (
    sharp_odds_snapshot as _sharp_snapshot,
    sharp_anchor_enabled as _sharp_enabled,
)
from backend.data.harvester import (
    queue_status,
    run_one_pass,
    seed_wc_squads,
)
from backend.data.harvester_seed import (
    LEAGUES as _SEED_LEAGUES,
    SEASONS as _SEED_SEASONS,
    seed_all_leagues,
    seed_full_stack,
    seed_heavy,
    seed_league_fixtures,
    seed_wc_fixture_players,
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
            "inventory": _inventory(),
            "sharp_odds": _sharp_overview(),
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


@router.post("/seed/wc-fixture-players")
async def post_seed_wc_fixture_players() -> dict:
    """One /fixtures/players call per completed WC fixture (resolved via
    MatchEvent.api_fixture_id). Fires the goalscorer market data fill —
    PlayerHistory rows accumulate as the harvester drains. ~36 calls today,
    higher priority than the league fan-out."""
    return seed_wc_fixture_players()


@router.post("/seed/heavy")
async def post_seed_heavy() -> dict:
    """Queue everything — all 21 leagues × 15 seasons + national teams +
    standings + topscorers + topassists + team stats + H2H + coaches +
    sidelined. Can add 200,000+ jobs. Use when quota is plentiful.
    Idempotent — calling twice adds 0 duplicate jobs."""
    return seed_heavy()


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


_FIXTURES_PER_TEAM_PER_FIXTURE = 2   # stats are one row per (fixture, team)


def _inventory() -> dict:
    """How much of our intended archive is actually in the database.

    Coverage = numerator / denominator where the denominator is *derived*
    from the seed lists (TEAM_IDS, LEAGUES, SEASONS) so it stays in sync
    when those change — no magic constants on the FE side.
    """
    from backend.db.models import (
        FixtureArchive,
        HarvestJob,
        HarvestRaw,
        PlayerHistory,
        PlayerProfile,
        PlayerTournamentStats,
    )
    from backend.db.session import SessionLocal

    db = SessionLocal()
    try:
        wc_team_ids = set(_WC_TEAM_IDS.values())

        wc_squad_teams = (
            db.query(func.count(func.distinct(PlayerProfile.team_id)))
            .filter(PlayerProfile.team_id.in_(wc_team_ids))
            .scalar()
            or 0
        )
        wc_player_profiles = (
            db.query(func.count(PlayerProfile.player_id))
            .filter(PlayerProfile.team_id.in_(wc_team_ids))
            .scalar()
            or 0
        )

        player_season_stats = db.query(func.count(PlayerTournamentStats.id)).scalar() or 0
        fixture_archives = db.query(func.count(FixtureArchive.id)).scalar() or 0
        player_history = db.query(func.count(PlayerHistory.id)).scalar() or 0

        raw_total_bytes = db.query(func.coalesce(func.sum(func.length(HarvestRaw.response_json)), 0)).scalar() or 0

        # Endpoint breakdown of completed jobs — what we've actually pulled.
        # We aggregate from harvest_jobs (small table, hot path) rather than
        # harvest_raw (large blob bodies) so this stays cheap.
        rows = (
            db.query(
                HarvestJob.endpoint,
                func.count(HarvestJob.id).label("done"),
                func.avg(HarvestJob.response_size_bytes).label("avg_bytes"),
                func.max(HarvestJob.completed_at).label("last_done"),
            )
            .filter(HarvestJob.status == "done")
            .group_by(HarvestJob.endpoint)
            .order_by(func.count(HarvestJob.id).desc())
            .limit(20)
            .all()
        )
        endpoint_breakdown = [
            {
                "endpoint": r.endpoint,
                "done": int(r.done or 0),
                "avg_bytes": int(r.avg_bytes or 0),
                "last_done": r.last_done.isoformat() if r.last_done else None,
            }
            for r in rows
        ]

        # 7-day activity timeline — count of done jobs per UTC day, oldest first.
        # Buckets are computed in Python from a per-row scan limited to the last
        # 8 days so the sparkline always has a stable axis.
        cutoff = datetime.utcnow() - timedelta(days=8)
        completed_rows = (
            db.query(HarvestJob.completed_at)
            .filter(HarvestJob.status == "done")
            .filter(HarvestJob.completed_at >= cutoff)
            .all()
        )
        buckets: dict[str, int] = {}
        for (c,) in completed_rows:
            if c is None:
                continue
            key = c.date().isoformat()
            buckets[key] = buckets.get(key, 0) + 1
        # Emit 7 days oldest-to-newest, padding zero where empty.
        timeline: list[dict] = []
        today = datetime.utcnow().date()
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            key = d.isoformat()
            timeline.append({"date": key, "completed": buckets.get(key, 0)})

        # Denominators — derived. Only two of the five cards have a bounded
        # target: WC squads (48 teams, no more) and the fixture archive (each
        # league × season has a known fixture count). The rest are accumulate-
        # over-time depth metrics — api-football's /players endpoint returns
        # any player ever rostered, plus one row per season they played, so
        # "have / 1248" reads as broken (overshoot) instead of useful. Show
        # them as raw counts and the operator gets a true picture: bounded
        # cards show coverage, unbounded cards show how much we own.
        wc_team_count = len(_WC_TEAM_IDS)
        # Only EPL + Bundesliga are seeded by default — the others are opt-in.
        # Match what seed_full_stack actually queues so coverage % reflects the
        # operator's true intent.
        default_league_ids = {39, 78}
        default_league_fixture_total = sum(
            l["fixtures"] for l in _SEED_LEAGUES if l["id"] in default_league_ids
        ) * len(_SEED_SEASONS) * _FIXTURES_PER_TEAM_PER_FIXTURE

        return {
            "coverage": [
                {
                    "key": "wc_squads",
                    "label": "WC squads indexed",
                    "have": int(wc_squad_teams),
                    "target": wc_team_count,
                    "unit": "teams",
                },
                {
                    "key": "fixture_archive",
                    "label": "Fixture stats archive",
                    "have": int(fixture_archives),
                    "target": default_league_fixture_total,
                    "unit": "team-fixtures (EPL + Bundesliga)",
                },
                {
                    "key": "wc_players",
                    "label": "WC player profiles",
                    "have": int(wc_player_profiles),
                    "target": None,  # api-football returns ALL ever-rostered players
                    "unit": "players",
                },
                {
                    "key": "player_seasons",
                    "label": "Player season-stat rows",
                    "have": int(player_season_stats),
                    "target": None,  # one row per (player × team × season)
                    "unit": "season-stats",
                },
                {
                    "key": "player_history",
                    "label": "Per-fixture player rows",
                    "have": int(player_history),
                    "target": None,  # open-ended — depth, not coverage
                    "unit": "rows",
                },
            ],
            "endpoint_breakdown": endpoint_breakdown,
            "activity_7d": timeline,
            "archive_bytes": int(raw_total_bytes),
        }
    finally:
        db.close()


@router.get("/inventory")
async def get_inventory() -> dict:
    """Standalone inventory endpoint — same payload that lands in /overview
    under `inventory`. Kept separate so an ops dashboard can poll just the
    inventory without re-fetching the whole overview."""
    return _inventory()


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


def _sharp_overview() -> dict:
    """Sharp-odds (Pinnacle via SportsGameOdds) snapshot for the admin card.

    Returns a small payload — counts + age + one sample event — so the
    overview round-trip stays light. The full event list is available via
    sharp_odds_snapshot() for any deeper debug view.
    """
    snap = _sharp_snapshot()
    events = snap.get("events") or []
    sample = events[0] if events else None
    return {
        "feature_enabled": _sharp_enabled(),
        "fetched_at": snap.get("fetched_at"),
        "age_seconds": snap.get("age_seconds"),
        "event_count": len(events),
        "sample": sample,
    }
