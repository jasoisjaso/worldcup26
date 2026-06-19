"""Backfill the persistent api-football archive for completed matches.

For every Match with status=='complete' that has NO archived events / lineups /
statistics / prediction, walk api-football once per fixture and persist
everything. Resolves fixture_id via /fixtures?league=1&season=2026 (1 request
for all 104 fixtures), then per-match fetches:
  * /fixtures/events?fixture=X
  * /fixtures/lineups?fixture=X
  * /fixtures/statistics?fixture=X
  * /predictions?fixture=X
  * /fixtures/headtohead?h2h=<hid>-<aid>  (only if no fresh H2H row yet)

Each match costs ~5 API calls. Budget: 28 matches * 5 = 140 calls (pro plan
budget is 7,500/day). Run once after deploy. Idempotent — re-running on an
already-archived match is a no-op apart from the resolve call.

Usage (inside backend container):
    python -m backend.data.backfill_archive            # dry-run
    python -m backend.data.backfill_archive --apply    # actually fetch + write
    python -m backend.data.backfill_archive --apply --only M025,M026,M027,M028
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta

import httpx

from backend.data.fetchers.injuries import TEAM_IDS
from backend.data.persistence import (
    persist_api_prediction,
    persist_events,
    persist_h2h,
    persist_lineups,
    persist_statistics,
    rebuild_player_tournament_stats,
    rebuild_team_season_stats,
)
from backend.db.models import (
    ApiFootballPrediction,
    LiveMatchState,
    Match,
    MatchEvent,
    MatchH2H,
    MatchLineup,
    MatchStatistics,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}
_H2H_REFRESH_DAYS = 30


async def _resolve_fixture_ids(client: httpx.AsyncClient, db) -> dict[str, int]:
    """One request → fixture_id_external for every WC2026 match.

    Returns {match_id: fixture_id}. Caches into LiveMatchState as a side effect
    so the live poller and prematch fetchers can pick them up later for free.
    """
    code_by_api = {v: k for k, v in TEAM_IDS.items()}
    r = await client.get(
        f"{_BASE}/fixtures",
        params={"league": 1, "season": 2026},
        headers=_HEADERS,
        timeout=30.0,
    )
    r.raise_for_status()
    fixtures = r.json().get("response", []) or []

    matches = db.query(Match).all()
    by_pair: dict[tuple[str, str], Match] = {(m.home_code, m.away_code): m for m in matches}
    resolved: dict[str, int] = {}
    for fx in fixtures:
        teams = fx.get("teams") or {}
        home_api = (teams.get("home") or {}).get("id")
        away_api = (teams.get("away") or {}).get("id")
        if not home_api or not away_api:
            continue
        home_code = code_by_api.get(home_api)
        away_code = code_by_api.get(away_api)
        if not home_code or not away_code:
            continue
        m = by_pair.get((home_code, away_code))
        if not m:
            continue
        fid = (fx.get("fixture") or {}).get("id")
        if fid:
            resolved[m.id] = fid

    # Cache into LiveMatchState for future use
    for mid, fid in resolved.items():
        existing = db.query(LiveMatchState).filter(LiveMatchState.match_id == mid).first()
        if not existing:
            db.add(LiveMatchState(match_id=mid, fixture_id_external=fid, status="NS"))
        elif not existing.fixture_id_external:
            existing.fixture_id_external = fid
    db.commit()

    return resolved


async def _fetch_events(client: httpx.AsyncClient, fid: int) -> list[dict]:
    try:
        r = await client.get(f"{_BASE}/fixtures/events", params={"fixture": fid}, headers=_HEADERS, timeout=15.0)
        return r.json().get("response", []) if r.status_code == 200 else []
    except Exception as exc:
        logger.warning("events fetch %s: %s", fid, exc)
        return []


async def _fetch_lineups(client: httpx.AsyncClient, fid: int) -> list[dict]:
    try:
        r = await client.get(f"{_BASE}/fixtures/lineups", params={"fixture": fid}, headers=_HEADERS, timeout=15.0)
        return r.json().get("response", []) if r.status_code == 200 else []
    except Exception as exc:
        logger.warning("lineups fetch %s: %s", fid, exc)
        return []


async def _fetch_stats_raw(client: httpx.AsyncClient, fid: int) -> list[dict]:
    try:
        r = await client.get(f"{_BASE}/fixtures/statistics", params={"fixture": fid}, headers=_HEADERS, timeout=15.0)
        return r.json().get("response", []) if r.status_code == 200 else []
    except Exception as exc:
        logger.warning("stats fetch %s: %s", fid, exc)
        return []


async def _fetch_prediction(client: httpx.AsyncClient, fid: int) -> dict | None:
    try:
        r = await client.get(f"{_BASE}/predictions", params={"fixture": fid}, headers=_HEADERS, timeout=15.0)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", []) or []
        return resp[0] if resp else None
    except Exception as exc:
        logger.warning("prediction fetch %s: %s", fid, exc)
        return None


async def _fetch_h2h(client: httpx.AsyncClient, hid: int, aid: int) -> list[dict]:
    try:
        r = await client.get(
            f"{_BASE}/fixtures/headtohead",
            params={"h2h": f"{hid}-{aid}", "last": 20},
            headers=_HEADERS,
            timeout=15.0,
        )
        return r.json().get("response", []) if r.status_code == 200 else []
    except Exception as exc:
        logger.warning("h2h fetch %s-%s: %s", hid, aid, exc)
        return []


def _is_empty(db, match_id: str) -> dict:
    return {
        "events": db.query(MatchEvent).filter(MatchEvent.match_id == match_id).count() == 0,
        "lineups": db.query(MatchLineup).filter(MatchLineup.match_id == match_id).count() == 0,
        "stats": db.query(MatchStatistics).filter(MatchStatistics.match_id == match_id).count() == 0,
        "prediction": db.query(ApiFootballPrediction).filter(ApiFootballPrediction.match_id == match_id).count() == 0,
    }


async def backfill(apply: bool = False, only: list[str] | None = None) -> dict:
    if not _API_KEY:
        print("[error] API_FOOTBALL_KEY not set", file=sys.stderr)
        return {"error": "no_api_key"}

    summary = {
        "matches_scanned": 0,
        "matches_processed": 0,
        "events": 0,
        "lineups": 0,
        "stats": 0,
        "predictions": 0,
        "h2h": 0,
        "skipped_already_full": 0,
        "unresolved_fixture": 0,
    }

    db = SessionLocal()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            print("[backfill] resolving fixture ids for all 104 fixtures (1 req)...")
            resolved = await _resolve_fixture_ids(client, db)
            print(f"[backfill] resolved {len(resolved)} fixtures")

            q = db.query(Match).filter(Match.status == "complete").order_by(Match.kickoff.asc())
            if only:
                q = q.filter(Match.id.in_(only))
            done = q.all()

            for m in done:
                summary["matches_scanned"] += 1
                empty = _is_empty(db, m.id)
                if not any(empty.values()):
                    summary["skipped_already_full"] += 1
                    continue

                fid = resolved.get(m.id)
                if not fid:
                    print(f"  {m.id}  no fixture id")
                    summary["unresolved_fixture"] += 1
                    continue

                if not apply:
                    print(f"  {m.id}  fixture={fid}  needs: " + ", ".join(k for k, v in empty.items() if v))
                    continue

                print(f"  {m.id}  fixture={fid}  fetching...")

                # Events
                if empty["events"]:
                    events = await _fetch_events(client, fid)
                    n = persist_events(db, m.id, fid, events)
                    summary["events"] += n
                    print(f"    + {n} events")

                # Lineups
                if empty["lineups"]:
                    raw = await _fetch_lineups(client, fid)
                    n = persist_lineups(db, m.id, fid, raw)
                    summary["lineups"] += n
                    print(f"    + {n} lineup players")

                # Statistics (lock as final)
                if empty["stats"]:
                    raw = await _fetch_stats_raw(client, fid)
                    n = persist_statistics(db, m.id, fid, raw, is_final=True)
                    summary["stats"] += n
                    print(f"    + {n} stat rows (locked as final)")

                # api-football prediction
                if empty["prediction"]:
                    raw = await _fetch_prediction(client, fid)
                    if raw:
                        ok = persist_api_prediction(db, m.id, fid, raw)
                        summary["predictions"] += 1 if ok else 0
                        print("    + prediction" if ok else "    (prediction empty)")

                # H2H — only if missing or stale
                hid = TEAM_IDS.get(m.home_code)
                aid = TEAM_IDS.get(m.away_code)
                if hid and aid:
                    t1, t2 = (hid, aid) if hid < aid else (aid, hid)
                    latest = (
                        db.query(MatchH2H)
                        .filter(MatchH2H.team1_id == t1, MatchH2H.team2_id == t2)
                        .order_by(MatchH2H.captured_at.desc())
                        .first()
                    )
                    needs_h2h = not latest or (datetime.utcnow() - latest.captured_at) > timedelta(days=_H2H_REFRESH_DAYS)
                    if needs_h2h:
                        raw = await _fetch_h2h(client, hid, aid)
                        n = persist_h2h(db, raw)
                        summary["h2h"] += n
                        if n:
                            print(f"    + {n} h2h fixtures")

                db.commit()
                summary["matches_processed"] += 1

            # Rebuild aggregates so /teams pages reflect the new lineup data
            if apply:
                print("[backfill] rebuilding player + team aggregates...")
                rebuild_player_tournament_stats(db, "WC2026")
                rebuild_team_season_stats(db, "WC2026")
                db.commit()

        return summary
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually write to DB (default: dry-run)")
    parser.add_argument("--only", help="Comma-separated match ids, e.g. M025,M026")
    args = parser.parse_args()
    only = [s.strip() for s in args.only.split(",")] if args.only else None
    summary = asyncio.run(backfill(apply=args.apply, only=only))
    print()
    print("== summary ==")
    for k, v in summary.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
