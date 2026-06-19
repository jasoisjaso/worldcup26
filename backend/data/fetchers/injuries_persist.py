"""Persistent injury layer.

The legacy `injuries.py` module caches injury counts in memory for the model's
lambda multiplier. This module additionally persists individual player records
into the `team_injuries` table so:
  - the UI can show a small "key player out" flag on bet-builder legs
  - the harvester pattern stays consistent (every API call writes raw + parsed)
  - we can re-process / sell the data later

One fetch per WC team per refresh cycle. ~48 calls per refresh. We deliberately
DO NOT run this every 30 minutes — daily injury data doesn't move that fast.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta

import httpx
from sqlalchemy import and_

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import TeamInjury
from backend.db.session import SessionLocal
from backend.data import quota_budget as _qb

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}


def _severity_from_reason(reason: str | None) -> str:
    if not reason:
        return "doubtful"
    r = (reason or "").lower()
    if any(k in r for k in ["surgery", "fractured", "broken", "torn", "tear", "long-term", "season-ended"]):
        return "out"
    if any(k in r for k in ["suspended", "suspension", "red card", "yellow card"]):
        return "out"
    if any(k in r for k in ["doubtful", "questionable"]):
        return "doubtful"
    if "probable" in r or "likely" in r:
        return "probable"
    return "doubtful"


async def refresh_team_injuries() -> dict:
    """One pass: fetch + persist injuries for every WC team. Gated by the
    shared quota budget so it never collides with backfill or steals the
    last calls from the live poller."""
    if not _API_KEY:
        return {"status": "no_api_key"}

    _qb.reset_if_new_day()
    if not _qb.injuries_can_run():
        return {"status": "skipped", "reason": "budget_gated"}

    total_fetched = 0
    total_persisted = 0
    quota_blocked = False

    async with httpx.AsyncClient(timeout=20.0) as client:
        for team_code, api_id in TEAM_IDS.items():
            if quota_blocked:
                break
            try:
                r = await client.get(
                    f"{_BASE}/injuries",
                    params={"team": api_id, "season": 2026},
                    headers=_HEADERS,
                    timeout=15.0,
                )
                if r.status_code != 200:
                    continue
                # Feed the shared quota counter after every call.
                remaining = None
                try:
                    remaining = int(r.headers.get("x-ratelimit-requests-remaining", ""))
                except Exception:
                    pass
                _qb.update_quota(remaining)
                body = r.json()
                if "request limit for the day" in str(body.get("errors", "")):
                    quota_blocked = True
                    break
                rows = body.get("response", []) or []
                total_fetched += 1
                _persist_for_team(team_code, rows)
                total_persisted += len(rows)
            except Exception as exc:
                logger.warning("injury fetch failed for %s: %s", team_code, exc)

    # Stale-row sweep: any TeamInjury not refreshed in 14+ days is treated as
    # recovered/no-longer-relevant and dropped. Conservative window so a single
    # feed glitch never erases a legitimate injury list.
    cleared = _sweep_stale_injuries(days=14)
    return {
        "teams_fetched": total_fetched,
        "rows_persisted": total_persisted,
        "stale_cleared": cleared,
        "quota_blocked": quota_blocked,
    }


def _sweep_stale_injuries(days: int) -> int:
    db = SessionLocal()
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        stale = db.query(TeamInjury).filter(TeamInjury.last_seen_at < cutoff).all()
        for row in stale:
            db.delete(row)
        db.commit()
        return len(stale)
    finally:
        db.close()


def _persist_for_team(team_code: str, rows: list[dict]) -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        seen_player_ids: set[int] = set()
        for row in rows:
            player = (row.get("player") or {})
            api_pid = player.get("id")
            if not api_pid:
                continue
            seen_player_ids.add(api_pid)
            name = player.get("name") or ""
            reason = player.get("reason") or row.get("reason") or ""
            severity = _severity_from_reason(reason)
            existing = (
                db.query(TeamInjury)
                .filter(and_(
                    TeamInjury.team_code == team_code,
                    TeamInjury.api_player_id == api_pid,
                ))
                .first()
            )
            if existing:
                existing.reason = reason
                existing.severity = severity
                existing.player_name = name
                existing.last_seen_at = now
            else:
                db.add(TeamInjury(
                    team_code=team_code,
                    api_player_id=api_pid,
                    player_name=name,
                    reason=reason,
                    severity=severity,
                    captured_at=now,
                    last_seen_at=now,
                ))
        db.commit()
    finally:
        db.close()


def get_injury_flags_for_match(home_code: str, away_code: str) -> dict:
    """Compact summary the bet builder can show as a small red flag.

    Returns {home: {out, doubtful, names}, away: {...}}."""
    db = SessionLocal()
    try:
        def for_team(code: str) -> dict:
            rows = db.query(TeamInjury).filter(TeamInjury.team_code == code).all()
            out = [r for r in rows if r.severity == "out"]
            doubt = [r for r in rows if r.severity == "doubtful"]
            names = [r.player_name for r in out if r.player_name]
            return {
                "out": len(out),
                "doubtful": len(doubt),
                "names": names[:5],
            }
        return {"home": for_team(home_code), "away": for_team(away_code)}
    finally:
        db.close()
