"""One-shot backfill of `severity` (on injury-shaped flags) and `first_seen`
(on thread / quote / news surfaces) for the existing team-news + match-brief
JSONs. The harvesters now write these fields on every fresh run; this script
gets the current production data caught up without waiting for a 60-minute
team-news re-harvest cycle.

Idempotent: re-running on already-backfilled data leaves it alone (severity
re-classifies the same way, first_seen only fills when missing).

Run:
  /usr/bin/python3.12 scripts/backfill_brief_fields.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_team_news import classify_severity

ROOT = Path(__file__).resolve().parent.parent
TEAM_NEWS = ROOT / "frontend" / "public" / "data" / "team-news.json"
MATCH_BRIEFS = ROOT / "frontend" / "public" / "data" / "match-briefs.json"

INJURY_KINDS = ("injury", "doubt", "ruled out", "miss", "fitness")


def backfill_flags(flags: list | None) -> tuple[list, int]:
    if not flags:
        return [], 0
    touched = 0
    out = []
    for f in flags:
        if not isinstance(f, dict):
            out.append(f)
            continue
        if "severity" not in f and f.get("kind") in INJURY_KINDS:
            f["severity"] = classify_severity(f.get("context", "") or "")
            touched += 1
        out.append(f)
    return out, touched


def backfill_first_seen(entry: dict, fallback_iso: str) -> int:
    """Stamp first_seen on each surface that doesn't have one. We use the
    parent payload's updated_at / harvested_at as the best guess; that's
    when the snapshot was captured, so 'NEW' badges will fire correctly
    for content added after this backfill."""
    touched = 0
    for key in ("thread", "quote", "news"):
        s = entry.get(key)
        if not isinstance(s, dict):
            continue
        if "first_seen" not in s:
            s["first_seen"] = fallback_iso
            touched += 1
    return touched


def backfill_team_news() -> None:
    if not TEAM_NEWS.exists():
        print(f"  {TEAM_NEWS} missing — skipping")
        return
    doc = json.loads(TEAM_NEWS.read_text())
    fallback = doc.get("updated_at") or (dt.datetime.utcnow().isoformat() + "Z")
    flag_touched = 0
    surface_touched = 0
    for code, entry in (doc.get("teams") or {}).items():
        if not isinstance(entry, dict):
            continue
        entry["flags"], n = backfill_flags(entry.get("flags"))
        flag_touched += n
        surface_touched += backfill_first_seen(entry, fallback)
    TEAM_NEWS.write_text(json.dumps(doc, indent=2))
    print(f"  team-news.json: severity added to {flag_touched} flags, first_seen added to {surface_touched} surfaces")


def backfill_match_briefs() -> None:
    if not MATCH_BRIEFS.exists():
        print(f"  {MATCH_BRIEFS} missing — skipping")
        return
    doc = json.loads(MATCH_BRIEFS.read_text())
    fallback_doc = doc.get("updated_at") or (dt.datetime.utcnow().isoformat() + "Z")
    flag_touched = 0
    surface_touched = 0
    for mid, brief in (doc.get("matches") or {}).items():
        if not isinstance(brief, dict):
            continue
        brief["flags"], n = backfill_flags(brief.get("flags"))
        flag_touched += n
        # Prefer the brief's own harvested_at if present — it's more accurate
        # than the doc-level updated_at.
        fb = brief.get("harvested_at") or fallback_doc
        surface_touched += backfill_first_seen(brief, fb)
    MATCH_BRIEFS.write_text(json.dumps(doc, indent=2))
    print(f"  match-briefs.json: severity added to {flag_touched} flags, first_seen added to {surface_touched} surfaces")


def main():
    print("Backfilling severity + first_seen on existing brief JSONs...")
    backfill_team_news()
    backfill_match_briefs()
    print("Done.")


if __name__ == "__main__":
    main()
