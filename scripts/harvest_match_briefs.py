"""Per-match community brief harvester for the WC26 site.

Runs the last30days engine once per upcoming match in the next 36 hours,
parses the EVIDENCE FOR SYNTHESIS block, and writes a JSON snapshot
consumed by the <MatchCommunityBrief> card on /match/[id]. Mirrors the
team-news pattern (item 1) but keyed on match_id.

Run on the VPS:
  /usr/bin/python3.12 scripts/harvest_match_briefs.py

Output: frontend/public/data/match-briefs.json

Data source for upcoming matches is the SQLite ledger at data/wc2026.db
(read-only). Frontend backend port isn't exposed on the VPS host, and
the DB lives next to the harvester on the same machine, so direct read
is the cleanest path.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

# Reuse the parsing helpers + TEAMS list + engine path from the team-news
# harvester. Keeps the markdown contract in one place.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from harvest_team_news import (
    ENGINE,
    PY312,
    TEAMS,
    _empty,
    _extract_flags,
    _extract_top_grounding,
    _extract_top_quote,
    _extract_top_reddit,
    _sentiment_corpus,
    classify_sentiment,
    stamp_first_seen,
)

ROOT = Path(__file__).resolve().parent.parent
DB = ROOT / "data" / "wc2026.db"
OUTPUT = ROOT / "frontend" / "public" / "data" / "match-briefs.json"
TMP_DIR = Path("/tmp/wc26-match-briefs")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# code -> human name, from the canonical 48-team list in harvest_team_news.
TEAM_NAME: dict[str, str] = dict(TEAMS)


def upcoming_matches(db_path: Path, hours_ahead: int) -> list[dict]:
    if not db_path.exists():
        raise FileNotFoundError(f"DB missing at {db_path}")
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    now = dt.datetime.utcnow()
    horizon = now + dt.timedelta(hours=hours_ahead)
    # Match the same statuses the backend treats as pre-kickoff. SQLite
    # DateTime columns come back as ISO strings via the ORM but sqlite3
    # compares strings lexicographically, which works for ISO-8601.
    cur.execute(
        """
        SELECT id, kickoff, home_code, away_code, status, "group", matchday, venue
        FROM matches
        WHERE status IN ('upcoming','scheduled','TBD','NS')
          AND kickoff >= ?
          AND kickoff <= ?
        ORDER BY kickoff ASC
        """,
        (now.isoformat(), horizon.isoformat()),
    )
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def run_engine_for_match(match_id: str, query: str, timeout: int, retries: int) -> Path | None:
    """Generic per-query engine call — match briefs use a 'Home vs Away' query
    rather than the single-team query that harvest_team_news uses."""
    out_path = TMP_DIR / f"{match_id}.md"
    cmd = [
        PY312, str(ENGINE),
        query,
        "--quick",
        "--emit", "md",
        "--subreddits", "soccer,worldcup,FIFA,soccerbetting",
        "--output", str(out_path),
        "--days", "15",
    ]
    attempts = retries + 1
    for attempt in range(1, attempts + 1):
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=timeout)
            return out_path
        except subprocess.TimeoutExpired:
            tag = f"timeout (attempt {attempt}/{attempts})" if attempts > 1 else "timeout"
            print(f"  [{match_id}] {tag}", flush=True)
        except subprocess.CalledProcessError as e:
            print(f"  [{match_id}] engine error: {e.stderr.decode()[:200]}", flush=True)
            return None
    return None


def parse_match_brief(md_path: Path, home_name: str, away_name: str) -> dict:
    """Reuse single-team parsers twice (home, away) and pick the higher-scoring
    result for each surface. Flags come from both sides (deduped by context)."""
    if not md_path.exists():
        return _empty_brief()
    text = md_path.read_text(encoding="utf-8", errors="ignore")
    body = text.split("<!-- EVIDENCE FOR SYNTHESIS")[-1].split("<!-- END EVIDENCE")[0]

    def best_of(extractor):
        h = extractor(body, home_name)
        a = extractor(body, away_name)
        if h is None: return a
        if a is None: return h
        # Both extractors return dicts with a 'score' field; tie-break by upvotes
        # where present, else fall back to home first.
        if (h.get("score", 0), h.get("upvotes") or 0) >= (a.get("score", 0), a.get("upvotes") or 0):
            return h
        return a

    news   = best_of(_extract_top_grounding)
    thread = best_of(_extract_top_reddit)
    quote  = best_of(_extract_top_quote)

    home_flags = _extract_flags(body, home_name)
    away_flags = _extract_flags(body, away_name)
    seen = set()
    flags: list[dict] = []
    for f in (*home_flags, *away_flags):
        key = (f["kind"], f["context"].lower())
        if key in seen:
            continue
        seen.add(key)
        flags.append(f)
    flags = flags[:5]  # keep room for both sides

    sentiment = classify_sentiment(_sentiment_corpus(news, thread, quote, flags))

    return {"news": news, "thread": thread, "quote": quote, "flags": flags, "sentiment": sentiment}


def _empty_brief() -> dict:
    return {"news": None, "thread": None, "quote": None, "flags": [], "sentiment": None}


def _is_empty_brief(b: dict | None) -> bool:
    if not b or not isinstance(b, dict):
        return True
    return not (any(b.get(k) for k in ("news", "thread", "quote")) or b.get("flags"))


def harvest_one(m: dict, timeout: int, retries: int) -> tuple[str, dict]:
    match_id: str = str(m["id"])
    home_code: str = str(m["home_code"])
    away_code: str = str(m["away_code"])
    home_name: str = TEAM_NAME.get(home_code) or home_code
    away_name: str = TEAM_NAME.get(away_code) or away_code
    query = f"{home_name} vs {away_name} World Cup 2026"
    t0 = time.time()
    md = run_engine_for_match(match_id, query, timeout=timeout, retries=retries)
    parsed = parse_match_brief(md, home_name, away_name) if md else _empty_brief()
    parsed["match_id"] = match_id
    parsed["home_code"] = home_code
    parsed["away_code"] = away_code
    parsed["kickoff"]   = m.get("kickoff")
    parsed["harvested_at"] = dt.datetime.utcnow().isoformat() + "Z"
    elapsed = time.time() - t0
    status = "OK" if not _is_empty_brief(parsed) else "EMPTY"
    print(f"  [{match_id}] {home_name} vs {away_name} {status} in {elapsed:.0f}s", flush=True)
    return match_id, parsed


def _load_existing() -> dict:
    if OUTPUT.exists():
        try:
            return json.loads(OUTPUT.read_text())
        except Exception:
            return {}
    return {}


def main():
    ap = argparse.ArgumentParser(description="Harvest per-match community briefs via last30days.")
    ap.add_argument("--hours", type=int, default=36, help="Look-ahead window in hours (default 36).")
    ap.add_argument("--timeout", type=int, default=600, help="Per-match engine timeout in seconds (default 600).")
    ap.add_argument("--retries", type=int, default=0, help="Retries after a timeout (default 0).")
    ap.add_argument("--workers", type=int, default=3, help="Thread pool size, default 3 (be polite to Reddit).")
    ap.add_argument("--match-id", action="append", help="If set, harvest only these match IDs (repeatable). Skips the upcoming-matches DB query.")
    args = ap.parse_args()

    if args.match_id:
        # Manual-target mode: pull the specific matches from the DB regardless of status/kickoff.
        conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        placeholders = ",".join("?" * len(args.match_id))
        cur = conn.execute(
            f'SELECT id, kickoff, home_code, away_code, status FROM matches WHERE id IN ({placeholders})',
            args.match_id,
        )
        targets = [dict(r) for r in cur.fetchall()]
        conn.close()
    else:
        targets = upcoming_matches(DB, args.hours)

    if not targets:
        print(f"No upcoming matches in next {args.hours}h. Nothing to do.")
        # Still rewrite OUTPUT with updated_at so the FE 'updated X ago' tag stays fresh.
        existing = _load_existing()
        existing_matches = (existing or {}).get("matches") or {}
        payload = {
            "updated_at": dt.datetime.utcnow().isoformat() + "Z",
            "match_count": len(existing_matches),
            "with_data": sum(1 for v in existing_matches.values() if not _is_empty_brief(v)),
            "matches": existing_matches,
        }
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(payload, indent=2))
        return 0

    print(f"Harvesting {len(targets)} matches (timeout={args.timeout}s, retries={args.retries}, workers={args.workers})...")
    for t in targets:
        print(f"  target: {t['id']:30} kickoff={t['kickoff']} {t['home_code']}-{t['away_code']}")

    t0 = time.time()
    results: dict[str, dict] = {}
    with cf.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(harvest_one, m, args.timeout, args.retries) for m in targets]
        for fut in cf.as_completed(futures):
            match_id, parsed = fut.result()
            results[match_id] = parsed

    # Merge: keep all prior briefs whose match isn't in this run's targets.
    # That way completed matches (no longer "upcoming") keep their final brief
    # snapshot until a future cleanup. Re-runs of the same match overwrite —
    # but we stamp first_seen so NEW badges only fire on genuinely-changed URLs.
    existing = _load_existing()
    existing_matches = (existing or {}).get("matches") or {}
    merged = dict(existing_matches)
    now_iso = dt.datetime.utcnow().isoformat() + "Z"
    for mid, parsed in results.items():
        merged[mid] = stamp_first_seen(parsed, existing_matches.get(mid), now_iso)

    payload = {
        "updated_at": dt.datetime.utcnow().isoformat() + "Z",
        "match_count": len(merged),
        "with_data": sum(1 for v in merged.values() if not _is_empty_brief(v)),
        "matches": merged,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT}")
    print(f"Total: {time.time() - t0:.0f}s")
    print(f"Matches with data: {payload['with_data']}/{payload['match_count']}")
    new_filled = sum(1 for mid in results if not _is_empty_brief(results[mid]))
    print(f"Newly filled this run: {new_filled}/{len(results)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
