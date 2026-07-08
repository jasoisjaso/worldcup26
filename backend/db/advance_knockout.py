"""Auto-advance the WC2026 knockout bracket (QF → SF → 3rd → Final).

R32 (M073-088) and R16 (M089-096) are seeded by seed_knockout.py / seed_r16.py.
From the Quarter-finals on, this module builds each round AUTOMATICALLY off
api-football's league-1 fixtures — the same authoritative feed the earlier
rounds were cross-checked against. api-football self-populates each knockout
round once the previous round's results settle, so wiring this into the
scheduler means the bracket "builds itself" the rest of the way.

Why source teams from api-football rather than resolving winners off our own
bracket tree: the tree in wc2026_bracket.json and some public schedules DISAGREE
on the semfinal pairing (tree: M101 = W97 v W98; some sources: SF1 = QF1 v QF3).
api-football is authoritative and removes the ambiguity — we just map its
fixtures onto our fixed M-id slots by (round, chronological order), which lines
up exactly with the published schedule:
    Quarter-finals  M097 07-09 → M100 07-12
    Semi-finals     M101 07-14 → M102 07-15
    3rd place       M103 07-18
    Final           M104 07-19

Idempotent: inserts a new fixture, updates an existing one only while it is
still 'upcoming', and never touches a row that has advanced (live/complete/etc).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

from backend.db.session import SessionLocal
from backend.db.models import Match, Team
from backend.data.fetchers.injuries import TEAM_IDS

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_WC_LEAGUE = 1
_WC_SEASON = 2026

# api-football team id -> our team code.
_API_ID_TO_CODE: dict[int, str] = {v: k for k, v in TEAM_IDS.items()}

# Fixed M-id schedule per knockout round, in chronological order. matchday:
# R16=5, QF=6, SF=7, 3rd-place + Final=8 (mirrors live_lifecycle taxonomy).
_ROUND_SLOTS: dict[str, tuple[int, list[str]]] = {
    "qf":    (6, ["M097", "M098", "M099", "M100"]),
    "sf":    (7, ["M101", "M102"]),
    "third": (8, ["M103"]),
    "final": (8, ["M104"]),
}

# Full "Stadium, City" venue strings by M-id (FIFA schedule) — api-football
# ships just "Gillette Stadium" without the city and leaves some null, so we
# format from here for consistency with the R32/R16 rows and use the api venue
# only as a fallback.
_FIFA_VENUE: dict[str, str] = {
    "M097": "Gillette Stadium, Foxborough",
    "M098": "SoFi Stadium, Los Angeles",
    "M099": "Hard Rock Stadium, Miami",
    "M100": "GEHA Field at Arrowhead Stadium, Kansas City",
    "M101": "AT&T Stadium, Dallas",
    "M102": "Mercedes-Benz Stadium, Atlanta",
    "M103": "Hard Rock Stadium, Miami",
    "M104": "MetLife Stadium, East Rutherford",
}


def _classify_round(round_name: str) -> str | None:
    """Map an api-football round label to our internal round key. Order matters —
    'Quarter-finals' and 'Semi-finals' both contain 'final', so those are tested
    before the plain Final."""
    r = (round_name or "").lower()
    if "quarter" in r:
        return "qf"
    if "semi" in r:
        return "sf"
    if "third" in r or "3rd" in r:
        return "third"
    if "final" in r:
        return "final"
    return None


def _code_for(team: dict, db) -> str | None:
    """Resolve an api-football team object to our team code — by id first
    (exact), then by name against the Team table as a belt-and-braces fallback."""
    code = _API_ID_TO_CODE.get(team.get("id"))
    if code:
        return code
    name = (team.get("name") or "").strip()
    if not name:
        return None
    t = db.query(Team).filter(Team.name == name).first()
    return t.code if t else None


def _kickoff_naive_utc(iso: str | None) -> datetime | None:
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
        return dt.replace(tzinfo=None) if dt.tzinfo else dt
    except Exception:
        return None


def _fetch_wc_fixtures() -> list[dict]:
    if not _API_KEY:
        logger.warning("advance_knockout: API_FOOTBALL_KEY not set")
        return []
    try:
        r = httpx.get(
            f"{_BASE}/fixtures",
            params={"league": _WC_LEAGUE, "season": _WC_SEASON},
            headers={"x-apisports-key": _API_KEY},
            timeout=20,
        )
        if r.status_code != 200:
            logger.warning("advance_knockout: fixtures HTTP %s", r.status_code)
            return []
        return r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("advance_knockout: fixture fetch failed: %s", exc)
        return []


def advance_knockout(verbose: bool = False) -> dict:
    """Seed/update QF→Final from api-football. Returns a summary dict."""
    summary: dict = {"inserted": 0, "updated": 0, "kept": 0, "skipped": 0, "matches": []}
    fixtures = _fetch_wc_fixtures()
    if not fixtures:
        summary["error"] = "no_fixtures"
        return summary

    # Bucket api fixtures by our round key.
    buckets: dict[str, list[dict]] = {}
    for f in fixtures:
        rk = _classify_round((f.get("league") or {}).get("round", ""))
        if rk in _ROUND_SLOTS:
            buckets.setdefault(rk, []).append(f)

    db = SessionLocal()
    try:
        for rk, (matchday, slots) in _ROUND_SLOTS.items():
            fx = buckets.get(rk, [])
            # Chronological order within the round == M-id order.
            fx.sort(key=lambda f: (f.get("fixture") or {}).get("date") or "")
            for slot_id, f in zip(slots, fx):
                teams = f.get("teams") or {}
                home = teams.get("home") or {}
                away = teams.get("away") or {}
                # A not-yet-drawn fixture has null/placeholder teams — skip until
                # api-football fills the real qualifiers.
                home_code = _code_for(home, db)
                away_code = _code_for(away, db)
                if not home_code or not away_code:
                    summary["skipped"] += 1
                    continue
                kickoff = _kickoff_naive_utc((f.get("fixture") or {}).get("date"))
                if kickoff is None:
                    summary["skipped"] += 1
                    continue
                api_venue = ((f.get("fixture") or {}).get("venue") or {}).get("name")
                venue = _FIFA_VENUE.get(slot_id) or api_venue or "TBD"

                existing = db.get(Match, slot_id)
                if existing is None:
                    db.add(Match(
                        id=slot_id, group=None, matchday=matchday,
                        kickoff=kickoff, venue=venue,
                        home_code=home_code, away_code=away_code, status="upcoming",
                    ))
                    summary["inserted"] += 1
                    action = "INSERT"
                elif existing.status == "upcoming":
                    existing.matchday = matchday
                    existing.kickoff = kickoff
                    existing.venue = venue
                    existing.home_code = home_code
                    existing.away_code = away_code
                    summary["updated"] += 1
                    action = "UPDATE"
                else:
                    summary["kept"] += 1
                    action = f"KEEP({existing.status})"
                summary["matches"].append(
                    {"id": slot_id, "action": action, "home": home_code, "away": away_code}
                )
                if verbose:
                    print(f"  {action} {slot_id}: {home_code} vs {away_code}  ({venue})")
        db.commit()
    finally:
        db.close()
    if verbose:
        print(f"Done. inserted={summary['inserted']} updated={summary['updated']} "
              f"kept={summary['kept']} skipped={summary['skipped']}")
    return summary


if __name__ == "__main__":
    import json
    print(json.dumps(advance_knockout(verbose=True), indent=2))
