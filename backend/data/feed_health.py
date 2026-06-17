"""Tracks the last successful run of each data feed so /health can surface staleness.

The product's whole trust claim is "every pick logged before kickoff". A feed that
quietly stops (a banned API key, a changed scrape target, an exhausted odds quota)
is worse than a crash because it is invisible. This registry makes silence visible:
each scheduler job records a success, and /health reports the age of each feed plus a
degraded flag when a feed is older than a grace multiple of its own interval.
"""
from datetime import datetime, timezone

# feed_id -> {"last_success": datetime|None, "label": str, "interval_minutes": int}
_FEEDS: dict[str, dict] = {}

# Grace multiple: a feed is only "stale" once it is this many times past its interval,
# so a single skipped run (cache hit, transient miss) does not trip the flag.
_GRACE = 3


def register(feed_id: str, label: str, interval_minutes: int) -> None:
    _FEEDS.setdefault(
        feed_id,
        {"last_success": None, "label": label, "interval_minutes": interval_minutes},
    )


def record(feed_id: str) -> None:
    """Mark a feed as having just succeeded. No-op for unregistered feeds."""
    info = _FEEDS.get(feed_id)
    if info is not None:
        info["last_success"] = datetime.now(timezone.utc)


def snapshot() -> dict:
    now = datetime.now(timezone.utc)
    feeds: dict[str, dict] = {}
    degraded: list[str] = []
    for fid, info in _FEEDS.items():
        ls = info["last_success"]
        age_min = None if ls is None else (now - ls).total_seconds() / 60.0
        stale = ls is None or (age_min is not None and age_min > info["interval_minutes"] * _GRACE)
        feeds[fid] = {
            "label": info["label"],
            "last_success": ls.isoformat() if ls else None,
            "age_minutes": round(age_min, 1) if age_min is not None else None,
            "interval_minutes": info["interval_minutes"],
            "stale": stale,
        }
        if stale:
            degraded.append(fid)
    return {"feeds": feeds, "degraded": sorted(degraded), "all_fresh": not degraded}
