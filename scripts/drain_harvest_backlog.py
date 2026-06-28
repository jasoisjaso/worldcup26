"""Drain the harvest_raw backlog by calling the existing run_one_pass loop until
empty. Runs IN-PROCESS in the backend container so it gets the same imports
and DB session config.

Each pass processes BATCH_SIZE blobs and commits. We loop until the processor
reports "idle" or we've made `--max-passes` iterations (safety cap).

Output is line-buffered progress so you can `tail -f` it from outside the
container while it runs.

Usage:
    docker exec wc26-backend python scripts/drain_harvest_backlog.py
    docker exec wc26-backend python scripts/drain_harvest_backlog.py --max-passes 100
"""
from __future__ import annotations

import argparse
import sys
import time

# Import the existing processor — same code path as the scheduled tick.
from backend.data import harvest_processor
from backend.db.session import SessionLocal
from backend.db.models import HarvestRaw


def remaining(db) -> int:
    return (
        db.query(HarvestRaw)
        .filter(HarvestRaw.processed == False)  # noqa: E712
        .filter(HarvestRaw.status_code == 200)
        .count()
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-passes", type=int, default=100000,
                    help="Safety cap on pass count (default: effectively unlimited).")
    ap.add_argument("--batch-size", type=int, default=None,
                    help="Override harvest_processor.BATCH_SIZE for this run.")
    ap.add_argument("--report-every", type=int, default=10,
                    help="Print a progress line every N passes.")
    args = ap.parse_args()

    if args.batch_size:
        harvest_processor.BATCH_SIZE = args.batch_size
        print(f"BATCH_SIZE overridden to {args.batch_size}")

    db = SessionLocal()
    start_remaining = remaining(db)
    db.close()
    print(f"Backlog at start: {start_remaining:,} unprocessed blobs")
    print(f"BATCH_SIZE = {harvest_processor.BATCH_SIZE}")
    print()

    t0 = time.time()
    total = {"processed": 0, "rows_written": 0, "sub_jobs_queued": 0, "errors": 0}
    pass_n = 0

    while pass_n < args.max_passes:
        pass_n += 1
        result = harvest_processor.run_one_pass()
        if result.get("status") == "idle":
            print(f"\n[pass {pass_n}] idle — backlog drained")
            break
        for k in ("processed", "rows_written", "sub_jobs_queued", "errors"):
            total[k] += result.get(k, 0)

        if pass_n % args.report_every == 0:
            db = SessionLocal()
            left = remaining(db)
            db.close()
            elapsed = time.time() - t0
            rate = total["processed"] / max(elapsed, 1e-6)
            eta = left / max(rate, 1e-6)
            print(
                f"[pass {pass_n:5d}] processed={total['processed']:>7,}  "
                f"rows_written={total['rows_written']:>7,}  errors={total['errors']:>4}  "
                f"remaining={left:>7,}  rate={rate:.1f}/s  ETA={eta/60:.1f}min",
                flush=True,
            )

    elapsed = time.time() - t0
    db = SessionLocal()
    end_remaining = remaining(db)
    db.close()
    print()
    print(f"DRAIN COMPLETE in {elapsed/60:.1f}min ({pass_n} passes)")
    print(f"  processed={total['processed']:,}  rows_written={total['rows_written']:,}  "
          f"errors={total['errors']}  sub_jobs_queued={total['sub_jobs_queued']:,}")
    print(f"  backlog: {start_remaining:,} → {end_remaining:,}")


if __name__ == "__main__":
    sys.exit(main())
