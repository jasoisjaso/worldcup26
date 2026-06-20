"""Per-team news + sentiment harvester for the WC26 site.

Runs the last30days engine once per WC team, parses the EVIDENCE FOR SYNTHESIS
block, and emits a single JSON snapshot consumed by the <TeamNews> card on
/team/[code]. No backend changes — the frontend reads the static file.

Run:
  /usr/bin/python3.12 scripts/harvest_team_news.py

Output: frontend/public/data/team-news.json

The engine takes ~30-60s per query; we run with a small thread pool so the
total harvest sits under ~5 minutes. Reddit's public JSON has no hard
rate limit short-term but we keep parallelism modest to be polite.
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path.home() / ".claude" / "skills" / "last30days" / "scripts" / "last30days.py"
PY312 = "/usr/bin/python3.12"
OUTPUT = ROOT / "frontend" / "public" / "data" / "team-news.json"
TMP_DIR = Path("/tmp/wc26-team-news")
TMP_DIR.mkdir(parents=True, exist_ok=True)

# 48 WC teams pulled from the production /groups endpoint on 2026-06-20.
TEAMS: list[tuple[str, str]] = [
    ("ar", "Argentina"), ("at", "Austria"), ("au", "Australia"),
    ("ba", "Bosnia and Herzegovina"), ("be", "Belgium"), ("br", "Brazil"),
    ("ca", "Canada"), ("cd", "DR Congo"), ("ch", "Switzerland"),
    ("ci", "Ivory Coast"), ("co", "Colombia"), ("cv", "Cape Verde"),
    ("cw", "Curacao"), ("cz", "Czechia"), ("de", "Germany"),
    ("dz", "Algeria"), ("ec", "Ecuador"), ("eg", "Egypt"),
    ("es", "Spain"), ("fr", "France"), ("gb-eng", "England"),
    ("gb-sct", "Scotland"), ("gh", "Ghana"), ("hr", "Croatia"),
    ("ht", "Haiti"), ("iq", "Iraq"), ("ir", "Iran"),
    ("jo", "Jordan"), ("jp", "Japan"), ("kr", "South Korea"),
    ("ma", "Morocco"), ("mx", "Mexico"), ("nl", "Netherlands"),
    ("no", "Norway"), ("nz", "New Zealand"), ("pa", "Panama"),
    ("pt", "Portugal"), ("py", "Paraguay"), ("qa", "Qatar"),
    ("sa", "Saudi Arabia"), ("se", "Sweden"), ("sn", "Senegal"),
    ("tn", "Tunisia"), ("tr", "Turkey"), ("us", "United States"),
    ("uy", "Uruguay"), ("uz", "Uzbekistan"), ("za", "South Africa"),
]

# Injury / availability keywords. Lower-cased substring match — keep tight so
# we don't flag mundane chatter. Words like "miss" are too noisy alone, so we
# only match "will miss" / "to miss" / "miss the".
FLAG_PATTERNS = [
    (re.compile(r"\binjur(y|ed|ies)\b", re.I), "injury"),
    (re.compile(r"\bdoubt(ful)?\b", re.I), "doubt"),
    (re.compile(r"\bsuspen(d|ded|sion)\b", re.I), "suspension"),
    (re.compile(r"\b(out for|sidelined|ruled out|withdrawn?|withdrew)\b", re.I), "ruled out"),
    (re.compile(r"\b(will miss|to miss|miss the|misses)\b", re.I), "miss"),
    (re.compile(r"\bfitness (concern|test|doubt)\b", re.I), "fitness"),
    (re.compile(r"\bred card\b", re.I), "red card"),
]


def run_engine(team_code: str, team_name: str) -> Path | None:
    """Run the last30days engine for one team. Returns path to the markdown
    output, or None on failure. We pin subreddits to soccer + worldcup so the
    engine doesn't waste a planning loop figuring them out."""
    out_path = TMP_DIR / f"{team_code}.md"
    cmd = [
        PY312, str(ENGINE),
        f"{team_name} World Cup 2026",
        "--quick",
        "--emit", "md",
        "--subreddits", "soccer,worldcup,FIFA,soccerbetting",
        "--output", str(out_path),
        "--days", "20",
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
        return out_path
    except subprocess.TimeoutExpired:
        print(f"  [{team_code}] timeout", flush=True)
        return None
    except subprocess.CalledProcessError as e:
        print(f"  [{team_code}] engine error: {e.stderr.decode()[:200]}", flush=True)
        return None


def parse_brief(md_path: Path, team_name: str) -> dict:
    """Pull top news + top thread + top quote + injury flags out of the
    engine's EVIDENCE FOR SYNTHESIS markdown block. We're parsing the engine's
    output format directly — see SKILL.md for the contract."""
    if not md_path.exists():
        return _empty()
    text = md_path.read_text(encoding="utf-8", errors="ignore")

    # Engine wraps the parse-target between two HTML comments.
    body = text.split("<!-- EVIDENCE FOR SYNTHESIS")[-1].split("<!-- END EVIDENCE")[0]

    news = _extract_top_grounding(body, team_name)
    thread = _extract_top_reddit(body, team_name)
    quote = _extract_top_quote(body, team_name)
    flags = _extract_flags(body, team_name)

    return {
        "news": news,
        "thread": thread,
        "quote": quote,
        "flags": flags,
    }


def _empty() -> dict:
    return {"news": None, "thread": None, "quote": None, "flags": []}


# Engine items inside a cluster look like:
#   1. [grounding] World Cup 2026 Power Rankings...
#      - 2026-06-19 | www.goal.com | score:44
#      - URL: https://...
#      - Evidence: ...
#   2. [reddit] Cape Verde players reactions...
#      - 2026-06-15 | r/soccer | [14,958pts, 237cmt] | score:38
#      - URL: https://...
# We walk items individually because a single cluster can mix sources.

ITEM_RX = re.compile(
    r"^\d+\.\s+\[(?P<source>grounding|reddit|hackernews|github)\]\s+(?P<title>.+?)$",
    re.M,
)


def _iter_items(body: str):
    """Yield (source, title, metadata_dict) tuples for every ranked item."""
    matches = list(ITEM_RX.finditer(body))
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        meta_block = body[start:end]

        # URL line: "   - URL: https://..."
        url_match = re.search(r"-\s+URL:\s*(\S+)", meta_block)
        # Date | source | score line. Reddit version has an extra stats segment.
        date_match = re.search(r"-\s+(\d{4}-\d{2}-\d{2})\s+\|\s+([^|]+?)\s+\|", meta_block)
        # Optional Reddit stats segment.
        stats_match = re.search(r"\[(\d[\d,]*)\s*pts,\s*(\d[\d,]*)\s*cmt\]", meta_block)
        # Score is on the same row.
        score_match = re.search(r"score:\s*(\d+)", meta_block)

        yield m.group("source"), m.group("title").strip().rstrip(" |"), {
            "url": url_match.group(1) if url_match else None,
            "date": date_match.group(1) if date_match else None,
            "source_label": date_match.group(2).strip() if date_match else None,
            "upvotes": int(stats_match.group(1).replace(",", "")) if stats_match else None,
            "comments": int(stats_match.group(2).replace(",", "")) if stats_match else None,
            "score": int(score_match.group(1)) if score_match else 0,
        }


# Team-name aliases. The engine demotes items that don't mention the entity, so
# matching on team_name alone misses "USA" articles for "United States" etc.
# Each list is lowercased substring patterns we accept as team-relevant.
TEAM_ALIASES: dict[str, list[str]] = {
    "United States": ["united states", "usa", " us "],
    "South Korea": ["south korea", "korea"],
    "DR Congo": ["dr congo", "congo"],
    "Bosnia and Herzegovina": ["bosnia"],
    "Cape Verde": ["cape verde", "cabo verde"],
    "Ivory Coast": ["ivory coast", "cote d'ivoire", "côte d'ivoire"],
    "Czechia": ["czechia", "czech republic", "czech"],
    "New Zealand": ["new zealand"],
    "Saudi Arabia": ["saudi arabia", "saudi"],
    "South Africa": ["south africa"],
}


def _team_match(text: str, team_name: str) -> bool:
    aliases = TEAM_ALIASES.get(team_name) or [team_name.lower()]
    t = text.lower()
    return any(a in t for a in aliases)


def _extract_top_grounding(body: str, team_name: str) -> dict | None:
    """Highest-scored team-specific web article. Score-ties broken by date
    (recent first). When everything's score 0 (entity-miss demotion), we still
    pick the most recent matching headline rather than nothing."""
    candidates = []
    for src, title, meta in _iter_items(body):
        if src != "grounding" or not meta["url"]:
            continue
        if not _team_match(title, team_name):
            continue
        candidates.append((meta["score"], meta["date"] or "", title, meta))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _score, _date, title, meta = candidates[0]
    return {
        "title": title,
        "url": meta["url"],
        "source": meta["source_label"],
        "date": meta["date"],
        "score": meta["score"],
    }


def _extract_top_reddit(body: str, team_name: str) -> dict | None:
    """Top team-specific reddit thread. Tie-break by upvotes when scores are
    all 0 — engine demotes when entity-resolution misses, but upvotes is still
    a meaningful signal."""
    candidates = []
    for src, title, meta in _iter_items(body):
        if src != "reddit" or not meta["url"] or not meta["url"].startswith("https://www.reddit.com"):
            continue
        if not _team_match(title, team_name):
            continue
        candidates.append((meta["score"], meta["upvotes"] or 0, title, meta))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (x[0], x[1]), reverse=True)
    _score, _upvotes, title, meta = candidates[0]
    return {
        "title": title,
        "url": meta["url"],
        "upvotes": meta["upvotes"],
        "comments": meta["comments"],
        "subreddit": meta["source_label"],
        "date": meta["date"],
        "score": meta["score"],
    }


COMMENT_RX = re.compile(
    r'-\s+"([^"]+?)"\s+—\s+(u/[\w-]+)\s+\((\d+)\s+upvotes\)\s+—\s+(\S+)',
    re.M,
)


def _extract_top_quote(body: str, team_name: str) -> dict | None:
    """Pull the highest-upvoted community comment that mentions the team. The
    Top Community Comments section is cross-team, so we filter to keep the
    /team/[code] surface relevant."""
    section = body.split("## Top Community Comments")
    if len(section) < 2:
        return None
    section_text = section[1].split("## ")[0]
    candidates = []
    for m in COMMENT_RX.finditer(section_text):
        candidate = {
            "body": m.group(1).strip(),
            "author": m.group(2),
            "upvotes": int(m.group(3)),
            "url": m.group(4),
        }
        if not _team_match(candidate["body"], team_name):
            continue
        candidates.append(candidate)
    if not candidates:
        return None
    return max(candidates, key=lambda c: c["upvotes"])


def _extract_flags(body: str, team_name: str) -> list[dict]:
    """Scan item titles for injury / suspension keywords. We deliberately
    don't scan the entire evidence body — it includes other teams' chatter
    and creates false positives. The item title is the strongest signal."""
    flags = []
    seen = set()
    team_lower = team_name.lower()
    for src, title, meta in _iter_items(body):
        # Only consider items that mention the team somewhere — keeps the flags
        # team-scoped instead of catching r/soccer cross-team chatter.
        if team_lower not in title.lower():
            continue
        for pat, kind in FLAG_PATTERNS:
            if not pat.search(title):
                continue
            context = title if len(title) < 140 else title[:137] + "..."
            key = (kind, context.lower())
            if key in seen:
                continue
            seen.add(key)
            flags.append({
                "kind": kind,
                "context": context,
                "source": src,
                "url": meta["url"],
            })
    return flags[:3]


def harvest_one(team_code: str, team_name: str) -> tuple[str, dict]:
    t0 = time.time()
    md = run_engine(team_code, team_name)
    parsed = parse_brief(md, team_name) if md else _empty()
    elapsed = time.time() - t0
    has_data = any(parsed[k] for k in ("news", "thread", "quote")) or parsed["flags"]
    status = "OK" if has_data else "EMPTY"
    print(f"  [{team_code}] {team_name} {status} in {elapsed:.0f}s", flush=True)
    return team_code, parsed


def main():
    print(f"Harvesting {len(TEAMS)} teams with last30days...")
    t0 = time.time()
    results: dict[str, dict] = {}

    with cf.ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(harvest_one, c, n) for c, n in TEAMS]
        for fut in cf.as_completed(futures):
            code, parsed = fut.result()
            results[code] = parsed

    payload = {
        "updated_at": dt.datetime.utcnow().isoformat() + "Z",
        "team_count": len(results),
        "with_data": sum(1 for v in results.values() if any(v[k] for k in ("news", "thread", "quote"))),
        "teams": dict(sorted(results.items())),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {OUTPUT}")
    print(f"Total: {time.time() - t0:.0f}s")
    print(f"Teams with data: {payload['with_data']}/{payload['team_count']}")


if __name__ == "__main__":
    sys.exit(main())
