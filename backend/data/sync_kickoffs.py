"""Reconcile our Match.kickoff times against api-football.

Pulls ALL World Cup 2026 fixtures (league=1, season=2026) from api-football, matches
each by home/away team api id, and diff vs our Match table. Prints any kickoff
mismatch. With --apply, writes the corrections.

Usage (inside backend container):
    python -m backend.data.sync_kickoffs            # dry-run
    python -m backend.data.sync_kickoffs --apply    # write corrections

Times are always stored UTC. The display layer renders to Brisbane via
toLocaleString(..., {timeZone: "Australia/Brisbane"}).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime

import httpx

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.models import Match
from backend.db.session import SessionLocal

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}


def fetch_all_wc_fixtures() -> list[dict]:
    """Return all fixtures for World Cup league/season."""
    with httpx.Client(timeout=30.0) as c:
        r = c.get(
            f"{_BASE}/fixtures",
            params={"league": 1, "season": 2026},
            headers=_HEADERS,
        )
        r.raise_for_status()
        return r.json().get("response", []) or []


def reconcile(apply: bool = False) -> dict:
    """Compare each DB Match.kickoff vs api-football. Optionally fix."""
    if not _API_KEY:
        print("[error] API_FOOTBALL_KEY not set", file=sys.stderr)
        return {"error": "no_api_key"}

    code_by_api = {v: k for k, v in TEAM_IDS.items()}
    fixtures = fetch_all_wc_fixtures()
    print(f"[sync] fetched {len(fixtures)} WC fixtures from api-football")

    db = SessionLocal()
    try:
        matches = db.query(Match).all()
        by_pair: dict[tuple[str, str], Match] = {
            (m.home_code, m.away_code): m for m in matches
        }

        changed = 0
        skipped = 0
        unmatched = 0
        wrong = []

        for fx in fixtures:
            fixture = fx.get("fixture") or {}
            iso = fixture.get("date")  # e.g. "2026-06-16T18:00:00+00:00"
            if not iso:
                continue
            try:
                # Normalize to UTC naive (since our DB stores naive UTC)
                if iso.endswith("Z"):
                    iso_z = iso[:-1] + "+00:00"
                else:
                    iso_z = iso
                api_dt = datetime.fromisoformat(iso_z)
                api_utc = api_dt.utctimetuple()
                api_naive = datetime(*api_utc[:6])
            except Exception as exc:
                print(f"[skip] bad date {iso}: {exc}")
                continue

            teams = fx.get("teams") or {}
            hid = (teams.get("home") or {}).get("id")
            aid = (teams.get("away") or {}).get("id")
            home_code = code_by_api.get(hid)
            away_code = code_by_api.get(aid)
            if not home_code or not away_code:
                unmatched += 1
                continue

            m = by_pair.get((home_code, away_code))
            if not m:
                unmatched += 1
                continue

            db_kickoff = m.kickoff
            if db_kickoff is None:
                wrong.append((m.id, home_code, away_code, None, api_naive, "missing"))
                if apply:
                    m.kickoff = api_naive
                    changed += 1
                continue

            # Compare
            if db_kickoff == api_naive:
                skipped += 1
                continue

            wrong.append((m.id, home_code, away_code, db_kickoff, api_naive, "drift"))
            if apply:
                m.kickoff = api_naive
                changed += 1

        if apply and changed:
            db.commit()
            print(f"[sync] committed {changed} corrections")

        # Report
        print(f"[sync] correct: {skipped}, wrong: {len(wrong)}, unmatched: {unmatched}")
        for mid, h, a, was, now, reason in wrong[:40]:
            was_s = was.isoformat() if was else "—"
            now_s = now.isoformat()
            from datetime import timedelta
            aest = now + timedelta(hours=10)
            print(f"  {mid} {h}-{a:6} DB:{was_s:20} → API:{now_s:20}  AEST:{aest.strftime('%a %d %b %H:%M')}  ({reason})")
        return {
            "correct": skipped,
            "wrong": len(wrong),
            "unmatched": unmatched,
            "applied": changed if apply else 0,
            "diffs": [
                {"match_id": mid, "was": was.isoformat() if was else None,
                 "now": now.isoformat(), "reason": r}
                for mid, _, _, was, now, r in wrong
            ],
        }
    finally:
        db.close()


if __name__ == "__main__":
    apply = "--apply" in sys.argv
    reconcile(apply=apply)
