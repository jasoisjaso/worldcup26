"""Datetime serialisation helper.

`Match.kickoff` (and similar DateTime columns) are stored as naive UTC. Python's
`datetime.isoformat()` on a naive value produces "2026-06-30T17:00:00" — no
timezone marker. JavaScript's `new Date("2026-06-30T17:00:00")` interprets a
no-tz string as **local time**, so a Brisbane user's browser reads it as
17:00 AEST = 07:00 UTC, ten hours off. This silently mis-renders every
kickoff time and breaks countdown widgets.

`iso_utc()` always emits the offset marker so every FE consumer parses it
unambiguously, no per-component workaround needed.

Discovered 2026-06-30 chasing a homepage countdown that read "in 3h" on a
match actually 13h away. The KickoffTime component had the workaround
already; 18+ other call sites did not. See AU timezone display memory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def iso_utc(dt: Optional[datetime]) -> Optional[str]:
    """ISO 8601 with explicit UTC offset for naive UTC datetimes.

    - None  -> None
    - naive -> assume UTC, append "+00:00"
    - aware -> isoformat as-is (already unambiguous)
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc).isoformat()
    return dt.isoformat()
