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

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.db.session import get_db

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
from backend.util.datetime import iso_utc
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
        CoachProfile,
        FixtureArchive,
        FixtureLineup,
        HarvestErrorLog,
        HarvestJob,
        HarvestRaw,
        PlayerHistory,
        PlayerProfile,
        PlayerSeasonStats,
        PlayerSidelined,
        PlayerTournamentStats,
        PlayerTransfer,
        StandingsHistory,
        TeamSeasonProfile,
    )
    from backend.db.session import SessionLocal
    from sqlalchemy import func

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

        # Queue breakdown by endpoint
        queue_by_endpoint = dict(
            db.query(HarvestJob.endpoint, func.count(HarvestJob.id))
            .filter(HarvestJob.status == "pending")
            .group_by(HarvestJob.endpoint)
            .order_by(func.count(HarvestJob.id).desc())
            .all()
        )

        return {
            "queue": by_status,
            "queue_by_endpoint": queue_by_endpoint,
            "raw_blobs": {
                "total": raw_total,
                "processed": raw_processed,
                "unprocessed": raw_total - raw_processed,
            },
            "tables": {
                "player_profiles": db.query(PlayerProfile).count(),
                "player_history": db.query(PlayerHistory).count(),
                "player_tournament_stats": db.query(PlayerTournamentStats).count(),
                "player_season_stats": db.query(PlayerSeasonStats).count(),
                "fixture_archives": db.query(FixtureArchive).count(),
                "fixture_lineups": db.query(FixtureLineup).count(),
                "team_season_profiles": db.query(TeamSeasonProfile).count(),
                "standings_history": db.query(StandingsHistory).count(),
                "coach_profiles": db.query(CoachProfile).count(),
                "player_transfers": db.query(PlayerTransfer).count(),
                "player_sidelined": db.query(PlayerSidelined).count(),
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
            "match_anomalies": _match_anomalies(db),
            "live_panel": _live_panel(db),
            "pick_performance": _pick_performance(db),
            "admin_actions": _admin_actions(db),
            "changelog": _changelog(),
            "settings": _rs.snapshot(),
            "build": {
                "commit": os.getenv("GIT_COMMIT", "unknown"),
            },
        }
    finally:
        db.close()


def _match_anomalies(db) -> dict:
    """Operator visibility into matches that are NOT in their expected
    lifecycle state. The dashboard tile shows the count + a flat list so
    we spot a FRA-IRQ-style problem (mismarked as complete) within one
    poll cycle, instead of weeks later when calibration drifts.

    Surfaces:
      - matches with Match.interruption_status set (delayed / postponed /
        abandoned / awarded) — these correctly skip calibration + pick
        settlement but the operator should still see them.
      - matches whose kickoff is >3h in the past but Match.status is
        still 'upcoming' AND no interruption_status — a true ghost row
        (live poller never fired, or stale-row sweep failed silently).
    """
    from backend.db.models import Match
    anomalies: list[dict] = []

    # Interrupted matches.
    for m in (
        db.query(Match)
        .filter(Match.interruption_status.isnot(None))
        .order_by(Match.kickoff.desc())
        .limit(50)
        .all()
    ):
        anomalies.append({
            "match_id": m.id,
            "label": f"{m.home_code} v {m.away_code}",
            "kickoff": iso_utc(m.kickoff),
            "status": m.status,
            "interruption_status": m.interruption_status,
            "interruption_reason": m.interruption_reason,
            "interruption_started_at": (
                m.interruption_started_at.isoformat()
                if m.interruption_started_at else None
            ),
            "partial_score": (
                f"{m.partial_home_score}-{m.partial_away_score}"
                if m.partial_home_score is not None and m.partial_away_score is not None
                else None
            ),
            "issue": "interrupted",
        })

    # Ghost rows — kicked off >3h ago but we never picked up FT.
    ghost_cutoff = datetime.utcnow() - timedelta(hours=3)
    for m in (
        db.query(Match)
        .filter(Match.status == "upcoming")
        .filter(Match.interruption_status.is_(None))
        .filter(Match.kickoff.isnot(None))
        .filter(Match.kickoff < ghost_cutoff)
        .order_by(Match.kickoff.desc())
        .limit(20)
        .all()
    ):
        anomalies.append({
            "match_id": m.id,
            "label": f"{m.home_code} v {m.away_code}",
            "kickoff": iso_utc(m.kickoff),
            "status": m.status,
            "interruption_status": None,
            "issue": "ghost_no_result",
        })

    by_issue: dict[str, int] = {}
    for a in anomalies:
        by_issue[a["issue"]] = by_issue.get(a["issue"], 0) + 1

    return {
        "count": len(anomalies),
        "by_issue": by_issue,
        "items": anomalies,
    }


@router.get("/match-anomalies")
async def get_match_anomalies() -> dict:
    """Dedicated endpoint for the dashboard tile — same payload that the
    /overview embeds under match_anomalies. Use this when you only want
    to refresh the anomalies card without re-polling the whole overview.
    """
    from backend.db.session import SessionLocal
    db = SessionLocal()
    try:
        return _match_anomalies(db)
    finally:
        db.close()


def _live_panel(db) -> dict:
    """Compact operator view of every currently-live match. One row per
    fixture with the data you actually look up during a live match:
    status, elapsed, score (+ shootout when applicable), tick freshness,
    push count for the last hour, and recent goal/card events.

    This is the daily-monitor view for tomorrow's MD3 simultaneous fixtures
    and next week's R32 onward — saves swapping between the public /live
    page and tailing logs to see what the harvester is actually doing.
    """
    from backend.data.fetchers.live_lifecycle import LIVE_STATUSES
    from backend.db.models import LiveMatchState, Match, MatchEvent, PushSent

    rows = (
        db.query(LiveMatchState, Match)
        .join(Match, Match.id == LiveMatchState.match_id)
        .filter(LiveMatchState.status.in_(list(LIVE_STATUSES)))
        .order_by(LiveMatchState.elapsed_min.desc())
        .all()
    )
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    items: list[dict] = []
    for lms, m in rows:
        # Recent events for this match — last 5 of any type.
        events = (
            db.query(MatchEvent)
            .filter(MatchEvent.match_id == m.id)
            .order_by(MatchEvent.elapsed.desc(), MatchEvent.id.desc())
            .limit(5)
            .all()
        )
        # Push notifications fired in the last hour for THIS match. The
        # dedup_key format from live.py is "swing:{match.id}:..." so a
        # prefix match counts every swing push for the fixture.
        push_count = (
            db.query(PushSent)
            .filter(PushSent.dedup_key.like(f"swing:{m.id}:%"))
            .filter(PushSent.sent_at >= one_hour_ago)
            .count()
        )
        tick_age_secs = (
            int((now - lms.updated_at).total_seconds())
            if lms.updated_at else None
        )
        items.append({
            "match_id": m.id,
            "label": f"{m.home_code} v {m.away_code}",
            "matchday": m.matchday,
            "group": m.group,
            "is_knockout": (m.matchday or 0) >= 4,
            "status": lms.status,
            "elapsed_min": lms.elapsed_min,
            "home_score": lms.home_score,
            "away_score": lms.away_score,
            "shootout_home_score": lms.shootout_home_score,
            "shootout_away_score": lms.shootout_away_score,
            "tick_age_secs": tick_age_secs,
            # 30s poll cadence → >2min without a tick is suspicious. Surfaces
            # the same kind of stale-row signal the sweep handles, before the
            # 5-min cutoff turns it into a sweep event.
            "stale": tick_age_secs is not None and tick_age_secs > 120,
            "push_count_1h": push_count,
            "recent_events": [
                {
                    "minute": (e.elapsed or 0) + (e.extra or 0),
                    "type": e.type,
                    "detail": e.detail,
                    "player": e.player_name,
                    "team": e.team_name,
                }
                for e in events
            ],
        })
    return {"count": len(items), "items": items}


def _pick_performance(db) -> dict:
    """Tournament-wide pick performance — the bottom-line
    "are we any good" signal. Reads from Prediction (which carries our
    probability + bookmaker odds + EV at logging) joined to Match (for
    the realised outcome). Skips matches with interruption_status set so
    voids don't pollute the unit-stake P&L.

    Stake model: flat 1u per logged pick (matches the picks UI default).
    Win returns (odds - 1) units; loss returns -1u. Push returns 0u (rare
    on 1X2 / Asian markets we currently log).

    Bucketed by market AND by confidence band (our_probability quintile)
    so a "all 1.4 favourites are winning but the +EV underdogs are
    losing money" signal jumps out.

    Window: the full tournament (45 days covers Jun 11 → Jul 19 plus a
    margin). Originally 30d, but the tournament is 38 days long so MD1
    picks started falling off the window once the semis arrived —
    silently shrinking the sample and distorting the trend.
    """
    from backend.db.models import Match, Prediction

    cutoff = datetime.utcnow() - timedelta(days=45)
    preds = (
        db.query(Prediction, Match)
        .join(Match, Match.id == Prediction.match_id)
        .filter(Prediction.logged_at >= cutoff)
        .filter(Match.status == "complete")
        .filter(Match.interruption_status.is_(None))
        .filter(Prediction.bookmaker_odds.isnot(None))
        .all()
    )

    def _outcome_won(market: str, m: Match) -> Optional[bool]:
        """Did the bet win? None if we don't know how to settle that market here."""
        if m.home_score is None or m.away_score is None:
            return None
        if market == "home_win":
            return m.home_score > m.away_score
        if market == "draw":
            return m.home_score == m.away_score
        if market == "away_win":
            return m.away_score > m.home_score
        if market == "btts_yes":
            return m.home_score > 0 and m.away_score > 0
        if market == "btts_no":
            return m.home_score == 0 or m.away_score == 0
        if market == "over_2_5":
            return (m.home_score + m.away_score) > 2.5
        if market == "under_2_5":
            return (m.home_score + m.away_score) < 2.5
        return None  # unknown market — exclude from bucket

    total_n = 0
    total_wins = 0
    total_stake = 0.0
    total_profit = 0.0
    clv_values: list[float] = []
    by_market: dict[str, dict] = {}
    by_confidence: dict[str, dict] = {}

    for p, m in preds:
        won = _outcome_won(p.market, m)
        if won is None:
            continue
        total_n += 1
        total_stake += 1.0
        profit = (p.bookmaker_odds - 1.0) if won else -1.0
        total_profit += profit
        if won:
            total_wins += 1
        if p.clv is not None:
            clv_values.append(p.clv)

        # By market
        mb = by_market.setdefault(p.market, {"n": 0, "wins": 0, "profit": 0.0})
        mb["n"] += 1
        mb["wins"] += 1 if won else 0
        mb["profit"] += profit

        # Confidence band by our_probability — quintiles 0-20% / 20-40% / ...
        band = "unknown"
        if p.our_probability is not None:
            q = int(p.our_probability * 5)  # 0..5
            q = min(4, max(0, q))
            edges = ["0-20%", "20-40%", "40-60%", "60-80%", "80-100%"]
            band = edges[q]
        cb = by_confidence.setdefault(band, {"n": 0, "wins": 0, "profit": 0.0})
        cb["n"] += 1
        cb["wins"] += 1 if won else 0
        cb["profit"] += profit

    def _summarise(bucket: dict) -> dict:
        n = bucket["n"]
        return {
            "n": n,
            "wins": bucket["wins"],
            "hit_rate": (bucket["wins"] / n) if n else None,
            "profit_u": round(bucket["profit"], 3),
            "roi": (bucket["profit"] / n) if n else None,
        }

    return {
        "window_days": 45,
        "total": {
            "n": total_n,
            "wins": total_wins,
            "hit_rate": (total_wins / total_n) if total_n else None,
            "stake_u": round(total_stake, 1),
            "profit_u": round(total_profit, 3),
            "roi": (total_profit / total_n) if total_n else None,
        },
        "clv": {
            "n": len(clv_values),
            "avg": (sum(clv_values) / len(clv_values)) if clv_values else None,
        },
        "by_market": {k: _summarise(v) for k, v in sorted(by_market.items())},
        "by_confidence": {k: _summarise(v) for k, v in sorted(by_confidence.items())},
    }


# In-process 5-min cache for the changelog so /overview polls don't burn
# the anonymous GitHub API quota (60/hr). 5 min is generous — commit cadence
# is multi-per-day not multi-per-minute. Per-process cache OK because the
# admin only has one container; if we scale out, replace with redis.
_CHANGELOG_CACHE: dict = {"at": 0.0, "data": None}
_CHANGELOG_TTL_SECONDS = 300


def _changelog() -> dict:
    """Last 20 commits — pulled from GitHub's public API and cached 5 min.

    Per dashboard-skill Part 9.3: 'changelog surface — operator catches up
    after vacation'. Solo-operator equivalent of release notes. We hit
    GitHub instead of running `git log` because the prod container doesn't
    ship .git (Dockerfile only COPYs source). Public-repo endpoint =
    anonymous 60/hr quota, far above what /overview polling needs.

    Returns {items, note}. note carries the failure reason when items is
    empty so the tile can show a single-line diagnostic instead of
    silent-failing.
    """
    import time
    import urllib.request
    import json as _json

    now = time.time()
    cached = _CHANGELOG_CACHE.get("data")
    if cached is not None and (now - _CHANGELOG_CACHE.get("at", 0.0)) < _CHANGELOG_TTL_SECONDS:
        return cached

    url = "https://api.github.com/repos/jasoisjaso/worldcup26/commits?per_page=20"
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "wc26-admin"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=4) as resp:
            if resp.status != 200:
                result = {"items": [], "note": f"github HTTP {resp.status}"}
            else:
                raw = _json.loads(resp.read().decode("utf-8"))
                items = []
                for c in raw:
                    commit = c.get("commit") or {}
                    author = commit.get("author") or {}
                    items.append({
                        "sha": (c.get("sha") or "")[:7],
                        "subject": (commit.get("message") or "").split("\n")[0][:120],
                        "iso": author.get("date"),
                        "author": author.get("name"),
                    })
                result = {"items": items, "note": None}
    except Exception as exc:
        result = {"items": [], "note": str(exc)[:120]}

    _CHANGELOG_CACHE["at"] = now
    _CHANGELOG_CACHE["data"] = result
    return result


@router.get("/changelog")
async def get_changelog() -> dict:
    """Dedicated endpoint for the Changelog tile."""
    return _changelog()


def _admin_actions(db) -> dict:
    """Last 50 entries from admin_actions, newest first.

    Powers the operator-facing 'Admin Actions' tile so any state-changing
    POST is visible in the dashboard within one poll cycle (15s). Each row
    surfaces the action name, when it was requested vs completed, status
    (ok / error / pending), and the error message if it failed.

    Catches the case where the audit table isn't yet present (very first
    request after deploy, before init_db runs) by returning an empty list
    silently — the dashboard tile renders an empty state in that case.
    """
    from backend.db.models import AdminAction
    try:
        rows = (
            db.query(AdminAction)
            .order_by(AdminAction.id.desc())
            .limit(50)
            .all()
        )
    except Exception:
        return {"count": 0, "items": []}
    items = [
        {
            "id": r.id,
            "action": r.action,
            "endpoint": r.endpoint,
            "requested_at": r.requested_at.isoformat() if r.requested_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            "status": r.status,
            "error": r.error,
        }
        for r in rows
    ]
    return {"count": len(items), "items": items}


@router.get("/admin-actions")
async def get_admin_actions() -> dict:
    """Dedicated endpoint for the Admin Actions tile."""
    from backend.db.session import SessionLocal
    db = SessionLocal()
    try:
        return _admin_actions(db)
    finally:
        db.close()


@router.get("/live-panel")
async def get_live_panel() -> dict:
    """Dedicated endpoint for the live-match tile so the UI can refresh
    every 10-30s without re-polling the whole /overview."""
    from backend.db.session import SessionLocal
    db = SessionLocal()
    try:
        return _live_panel(db)
    finally:
        db.close()


@router.get("/pick-performance")
async def get_pick_performance() -> dict:
    """Dedicated endpoint for the pick-performance tile. Same payload that
    /overview embeds under pick_performance."""
    from backend.db.session import SessionLocal
    db = SessionLocal()
    try:
        return _pick_performance(db)
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
#
# Every POST handler below wears @audited so a row lands in admin_actions
# before the action fires + after it returns (status="ok") or raises
# (status="error", error captured). The dashboard's Admin Actions tile
# tails this table so any silent misfire is visible within one poll cycle.
# Per dashboard-skill hygiene #1.
# ---------------------------------------------------------------------------


def audited(action_name: str):
    """Decorator that writes a row to admin_actions for each invocation.

    Safe-by-default — any failure during audit writing is caught so the
    operation itself isn't blocked by a logging failure (rare: only if
    the DB is offline or the table missing pre-init_db). The action still
    fires, just without the audit row. Logged at warning level instead.
    """
    from functools import wraps as _wraps

    def deco(fn):
        @_wraps(fn)
        async def wrapper(*args, **kwargs):
            from backend.db.session import SessionLocal as _SL
            from backend.db.models import AdminAction as _AA
            db = _SL()
            rec = None
            try:
                rec = _AA(action=action_name, endpoint=fn.__name__, status="pending")
                db.add(rec)
                db.commit()
                db.refresh(rec)
            except Exception as audit_exc:
                # Don't block the real action just because audit failed.
                db.rollback()
                import logging as _l
                _l.getLogger(__name__).warning("audit pre-write failed for %s: %s", action_name, audit_exc)
                rec = None
            try:
                result = await fn(*args, **kwargs) if _is_coroutine(fn) else fn(*args, **kwargs)
                if rec is not None:
                    try:
                        rec.status = "ok"
                        rec.completed_at = datetime.utcnow()
                        db.commit()
                    except Exception:
                        db.rollback()
                return result
            except Exception as exc:
                if rec is not None:
                    try:
                        rec.status = "error"
                        rec.error = str(exc)[:500]
                        rec.completed_at = datetime.utcnow()
                        db.commit()
                    except Exception:
                        db.rollback()
                raise
            finally:
                db.close()
        return wrapper
    return deco


def _is_coroutine(fn):
    import inspect
    return inspect.iscoroutinefunction(fn)


@router.post("/seed/wc-squads")
@audited("seed-wc-squads")
async def post_seed_wc_squads() -> dict:
    """One job per WC team — fetch the current squad. ~48 jobs queued."""
    return seed_wc_squads()


@router.post("/seed/full")
@audited("seed-full")
async def post_seed_full() -> dict:
    """WC player stats + EPL/Bundesliga fixtures. Dedup-safe."""
    return seed_full_stack()


@router.post("/seed/leagues")
@audited("seed-leagues")
async def post_seed_leagues() -> dict:
    """League fixtures for EPL + Bundesliga only."""
    return seed_league_fixtures()


@router.post("/seed/all-leagues")
@audited("seed-all-leagues")
async def post_seed_all_leagues() -> dict:
    """All 9 leagues × 2 seasons. Heavy queue — ~4,600 fixture jobs."""
    return seed_all_leagues()


@router.post("/seed/wc-fixture-players")
@audited("seed-wc-fixture-players")
async def post_seed_wc_fixture_players() -> dict:
    """One /fixtures/players call per completed WC fixture (resolved via
    MatchEvent.api_fixture_id). Fires the goalscorer market data fill —
    PlayerHistory rows accumulate as the harvester drains. ~36 calls today,
    higher priority than the league fan-out."""
    return seed_wc_fixture_players()


@router.post("/seed/heavy")
@audited("seed-heavy")
async def post_seed_heavy() -> dict:
    """Queue everything — all 21 leagues × 15 seasons + national teams +
    standings + topscorers + topassists + team stats + H2H + coaches +
    sidelined. Can add 200,000+ jobs. Use when quota is plentiful.
    Idempotent — calling twice adds 0 duplicate jobs."""
    return seed_heavy()


@router.post("/run-one")
@audited("run-one")
async def post_run_one() -> dict:
    """Force a single tick of the harvester (useful for manual backfill)."""
    return await run_one_pass()


@router.post("/pause")
@audited("pause")
async def post_pause() -> dict:
    """Pause every api-football harvester consumer until /resume is called.

    The live poller (scores/events) is intentionally NOT paused — the UI still
    needs live data during a match. This freezes the slow background fillers,
    which are where the bulk of the daily quota actually goes.
    """
    _rs.set_harvest_paused(True)
    return {"paused": True, "harvester_enabled": _qb.harvester_enabled()}


@router.post("/resume")
@audited("resume")
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


# ---------------------------------------------------------------------------
# Platt calibration (2026-06-30) — fit + read fitted params from the admin UI.
# ---------------------------------------------------------------------------

from backend.models import platt_calibration as _platt


@router.get("/platt/status")
def platt_status() -> dict:
    """Read the currently-cached Platt params + the feature-flag state."""
    p = _platt.load_params()
    return {
        "enabled": _platt.is_enabled(),
        "params": {
            "home": {"a": p.home.a, "b": p.home.b},
            "draw": {"a": p.draw.a, "b": p.draw.b},
            "away": {"a": p.away.a, "b": p.away.b},
        },
        "fitted_at": p.fitted_at,
        "n_samples": p.n_samples,
        "train_brier_before": p.train_brier_before,
        "train_brier_after": p.train_brier_after,
        "note": p.note,
    }


@router.post("/platt/refit")
def platt_refit(db: Session = Depends(get_db)) -> dict:
    """Refit Platt parameters from the latest model_calibration_log and persist.

    Safe to call any time; returns the new params payload (same shape as
    /platt/status) so the FE can show the before/after Brier delta and
    confirm the fit hasn't gone unstable (a < 0.1 or b > 2 are flags).
    """
    params = _platt.fit_from_db(db)
    _platt.save_params(params)
    return {
        "params": {
            "home": {"a": params.home.a, "b": params.home.b},
            "draw": {"a": params.draw.a, "b": params.draw.b},
            "away": {"a": params.away.a, "b": params.away.b},
        },
        "fitted_at": params.fitted_at,
        "n_samples": params.n_samples,
        "train_brier_before": params.train_brier_before,
        "train_brier_after": params.train_brier_after,
        "note": params.note,
    }
