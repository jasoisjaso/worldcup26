"""Demote pending 2023-season fan-out jobs to back-of-queue priority.

Reversible (just reset priority back to 250). Zero API calls. Zero deletions.

How it identifies 2023 vs 2024:
- The 4 /fixtures jobs (39/2023, 39/2024, 78/2023, 78/2024) have been completed
  and their raw responses are in HarvestRaw with the fixture IDs.
- We parse each raw response, extract the set of fixture IDs that belong to
  2023 (EPL + Bundesliga combined).
- Any pending HarvestJob whose params['fixture'] is in that set gets priority
  bumped to 900 (well below the 200-300 range the harvester normally pulls
  from, so they sit untouched while 2024 jobs drain).

To REVERT: rerun this script with --revert. Re-pulls the same fixture set
and sets their priority back to 250.
"""
from __future__ import annotations
import argparse
import json
import sys

from sqlalchemy import func
from backend.db.session import SessionLocal
from backend.db.models import HarvestJob, HarvestRaw

DEFERRED_PRIORITY = 900
RESTORED_PRIORITY = 250

# Endpoints whose per-fixture jobs we want to gate. The /fixtures league-level
# job itself is already done; we only touch its downstream fan-out.
FAN_OUT_ENDPOINTS = {"/fixtures/statistics", "/fixtures/events", "/predictions",
                     "/fixtures/lineups", "/odds"}

# The seeded league-season combos we want to demote. EPL=39, Bundesliga=78.
DEMOTE_LEAGUE_SEASONS = [(39, 2023), (78, 2023)]


def _fixture_ids_for(db, league: int, season: int) -> set[int]:
    """Pull every fixture id we got back from /fixtures for this (league, season)."""
    # Find the HarvestJob -> HarvestRaw pair for this league-season combo.
    target_dedup = None
    for j in db.query(HarvestJob).filter(HarvestJob.endpoint == "/fixtures").all():
        p = json.loads(j.params_json)
        if p.get("league") == league and p.get("season") == season:
            target_dedup = j.id
            break
    if target_dedup is None:
        return set()
    raw = (
        db.query(HarvestRaw)
        .filter(HarvestRaw.job_id == target_dedup)
        .filter(HarvestRaw.status_code == 200)
        .order_by(HarvestRaw.id.desc())
        .first()
    )
    if not raw:
        return set()
    try:
        body = json.loads(raw.response_json) or {}
    except Exception:
        return set()
    out: set[int] = set()
    for fx in (body.get("response") or []):
        fid = ((fx.get("fixture") or {}).get("id"))
        if fid:
            out.add(int(fid))
    return out


def main(revert: bool, dry_run: bool):
    db = SessionLocal()
    try:
        all_target_ids: set[int] = set()
        for league, season in DEMOTE_LEAGUE_SEASONS:
            ids = _fixture_ids_for(db, league, season)
            print(f"  league={league} season={season}: {len(ids)} fixture ids found")
            all_target_ids |= ids
        if not all_target_ids:
            print("FATAL: no target fixture IDs found — refusing to act.")
            return 1
        print(f"\nTotal target fixture IDs (2023 combined): {len(all_target_ids)}")

        # Sample 5 fixture IDs to sanity-check.
        print(f"Sample fixture IDs: {list(all_target_ids)[:5]}")
        print()

        # Find every pending job whose params['fixture'] is in the target set.
        # We scan all pending fan-out jobs in one query then filter in Python
        # because SQLite has no JSON operator that's portable across our build.
        target_priority = RESTORED_PRIORITY if revert else DEFERRED_PRIORITY
        current_filter = DEFERRED_PRIORITY if revert else RESTORED_PRIORITY

        pending = (
            db.query(HarvestJob)
            .filter(HarvestJob.status == "pending")
            .filter(HarvestJob.endpoint.in_(list(FAN_OUT_ENDPOINTS)))
            .all()
        )
        to_change: list[HarvestJob] = []
        for j in pending:
            try:
                p = json.loads(j.params_json)
            except Exception:
                continue
            fid = p.get("fixture")
            if fid and int(fid) in all_target_ids and j.priority != target_priority:
                to_change.append(j)

        print(f"=== {'DRY-RUN' if dry_run else 'APPLYING'}: {'restore' if revert else 'demote'} ===")
        print(f"jobs to change: {len(to_change)} (target priority = {target_priority})")

        # Endpoint breakdown of the change set.
        breakdown: dict[str, int] = {}
        for j in to_change:
            breakdown[j.endpoint] = breakdown.get(j.endpoint, 0) + 1
        for ep, n in sorted(breakdown.items()):
            print(f"  {ep:35s} {n:>5}")

        if dry_run:
            print("\nDRY-RUN — no changes made. Re-run with --apply to commit.")
            return 0

        for j in to_change:
            j.priority = target_priority
        db.commit()
        print(f"\nCommitted: {len(to_change)} job priorities updated.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="Actually commit changes")
    ap.add_argument("--revert", action="store_true", help="Restore priorities instead of demoting")
    args = ap.parse_args()
    sys.exit(main(revert=args.revert, dry_run=not args.apply))
