"""Seed the WC2026 knockout fixtures (Round of 32 first).

Resolves the official FIFA Round of 32 bracket from completed group standings:
  - matchday 4 = Round of 32 (16 fixtures, M073-M088)
  - kickoff + venue from FIFA's published schedule
  - home/away team codes from current standings + Annex C third-place table
    (the same `tournament_sim.load_bracket().third_table` we already use)

Run: `python -m backend.db.seed_knockout`
Idempotent: re-running updates kickoff/venue/teams if anything moved but never
overwrites a status that has already advanced past "upcoming".

Subsequent rounds (R16 / QF / SF / F) get seeded by `seed_next_round.py` after
each round settles — see docs/OPERATIONS.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from backend.db.session import init_db, SessionLocal
from backend.db.models import Match, Team
from backend.models.tournament_sim import load_bracket


# Official R32 fixtures from FIFA. Kickoffs in UTC.
# `home_slot` / `away_slot` are bracket-rule strings like "1A" (group A winner),
# "2C" (group C runner-up), "3X" (third-place from group X resolved at seed
# time via the Annex C third_table).
R32_FIXTURES: list[dict] = [
    {"id": "M073", "matchday": 4, "kickoff": "2026-06-28T19:00:00",
     "venue": "SoFi Stadium, Los Angeles",            "home_slot": "2A", "away_slot": "2B"},
    {"id": "M074", "matchday": 4, "kickoff": "2026-06-29T20:30:00",
     "venue": "Gillette Stadium, Foxborough",          "home_slot": "1E", "away_slot": "3-M74"},
    {"id": "M075", "matchday": 4, "kickoff": "2026-06-30T01:00:00",
     "venue": "Estadio BBVA, Monterrey",               "home_slot": "1F", "away_slot": "2C"},
    {"id": "M076", "matchday": 4, "kickoff": "2026-06-29T17:00:00",
     "venue": "NRG Stadium, Houston",                  "home_slot": "1C", "away_slot": "2F"},
    {"id": "M077", "matchday": 4, "kickoff": "2026-06-30T21:00:00",
     "venue": "MetLife Stadium, New York",             "home_slot": "1I", "away_slot": "3-M77"},
    {"id": "M078", "matchday": 4, "kickoff": "2026-06-30T17:00:00",
     "venue": "AT&T Stadium, Dallas",                  "home_slot": "2E", "away_slot": "2I"},
    {"id": "M079", "matchday": 4, "kickoff": "2026-07-01T01:00:00",
     "venue": "Estadio Azteca, Mexico City",           "home_slot": "1A", "away_slot": "3-M79"},
    {"id": "M080", "matchday": 4, "kickoff": "2026-07-01T16:00:00",
     "venue": "Mercedes-Benz Stadium, Atlanta",        "home_slot": "1L", "away_slot": "3-M80"},
    {"id": "M081", "matchday": 4, "kickoff": "2026-07-02T00:00:00",
     "venue": "Levi Stadium, Santa Clara",             "home_slot": "1D", "away_slot": "3-M81"},
    {"id": "M082", "matchday": 4, "kickoff": "2026-07-01T20:00:00",
     "venue": "Lumen Field, Seattle",                  "home_slot": "1G", "away_slot": "3-M82"},
    {"id": "M083", "matchday": 4, "kickoff": "2026-07-02T23:00:00",
     "venue": "BMO Field, Toronto",                    "home_slot": "2K", "away_slot": "2L"},
    {"id": "M084", "matchday": 4, "kickoff": "2026-07-02T19:00:00",
     "venue": "SoFi Stadium, Los Angeles",             "home_slot": "1H", "away_slot": "2J"},
    {"id": "M085", "matchday": 4, "kickoff": "2026-07-03T03:00:00",
     "venue": "BC Place, Vancouver",                   "home_slot": "1B", "away_slot": "3-M85"},
    {"id": "M086", "matchday": 4, "kickoff": "2026-07-03T22:00:00",
     "venue": "Hard Rock Stadium, Miami",              "home_slot": "1J", "away_slot": "2H"},
    {"id": "M087", "matchday": 4, "kickoff": "2026-07-04T01:30:00",
     "venue": "Arrowhead Stadium, Kansas City",        "home_slot": "1K", "away_slot": "3-M87"},
    {"id": "M088", "matchday": 4, "kickoff": "2026-07-03T18:00:00",
     "venue": "AT&T Stadium, Dallas",                  "home_slot": "2D", "away_slot": "2G"},
]


def _read_standings(db) -> dict[str, list[str]]:
    """Return {group: [team_code_1st, _2nd, _3rd, _4th]} using FIFA tiebreakers
    (points → GD → GF). Mirrors `bracket_live._read_standings` so the seed and
    the live bracket view stay aligned.
    """
    matches = db.query(Match).filter(Match.status == "complete").all()
    per_group: dict[str, dict[str, dict]] = {}
    for m in matches:
        if not m.group:
            continue
        g = m.group
        bucket = per_group.setdefault(g, {})
        for code in (m.home_code, m.away_code):
            bucket.setdefault(code, {"pts": 0, "gf": 0, "ga": 0})
        h, a = bucket[m.home_code], bucket[m.away_code]
        h["gf"] += (m.home_score or 0); h["ga"] += (m.away_score or 0)
        a["gf"] += (m.away_score or 0); a["ga"] += (m.home_score or 0)
        if (m.home_score or 0) > (m.away_score or 0):
            h["pts"] += 3
        elif (m.away_score or 0) > (m.home_score or 0):
            a["pts"] += 3
        else:
            h["pts"] += 1; a["pts"] += 1

    standings: dict[str, list[str]] = {}
    for g, codes in per_group.items():
        for c in codes:
            codes[c]["gd"] = codes[c]["gf"] - codes[c]["ga"]
        ranked = sorted(codes.items(), key=lambda kv: (kv[1]["pts"], kv[1]["gd"], kv[1]["gf"]), reverse=True)
        standings[g] = [c for c, _ in ranked]
    return standings


def _qualifying_thirds(db, standings: dict[str, list[str]]) -> list[str]:
    """Best 8 third-place groups by (pts, gd, gf)."""
    pool = []
    for g, codes in standings.items():
        if len(codes) < 3:
            continue
        third = codes[2]
        m_stats = db.query(Match).filter(
            Match.group == g, Match.status == "complete",
            (Match.home_code == third) | (Match.away_code == third),
        ).all()
        pts = gf = ga = 0
        for m in m_stats:
            if m.home_code == third:
                gf += m.home_score or 0; ga += m.away_score or 0
                if (m.home_score or 0) > (m.away_score or 0): pts += 3
                elif (m.home_score or 0) == (m.away_score or 0): pts += 1
            else:
                gf += m.away_score or 0; ga += m.home_score or 0
                if (m.away_score or 0) > (m.home_score or 0): pts += 3
                elif (m.home_score or 0) == (m.away_score or 0): pts += 1
        pool.append((pts, gf - ga, gf, g))
    pool.sort(reverse=True)
    return [g for _, _, _, g in pool[:8]]


def _resolve_slot(slot: str, standings: dict[str, list[str]], third_assignment: dict[str, str]) -> str | None:
    """Resolve a slot string to a team code.

    Slot grammar:
      "1A" → group A winner          → standings["A"][0]
      "2C" → group C runner-up       → standings["C"][1]
      "3-M74" → 3rd-place team that Annex C assigns to R32 match M74
    """
    if slot.startswith("3-"):
        match_no = slot[2:]
        g = third_assignment.get(match_no)
        if not g or g not in standings or len(standings[g]) < 3:
            return None
        return standings[g][2]
    rank = int(slot[0])
    g = slot[1:]
    if g not in standings or len(standings[g]) < rank:
        return None
    return standings[g][rank - 1]


def seed_r32(verbose: bool = True) -> dict:
    """Insert/update the 16 R32 fixtures. Returns a summary dict."""
    init_db()
    db = SessionLocal()
    summary = {"inserted": 0, "updated": 0, "skipped": [], "matches": []}
    try:
        standings = _read_standings(db)
        if len(standings) != 12:
            raise RuntimeError(f"Expected 12 group standings, got {len(standings)}: {sorted(standings)}")

        thirds = sorted(_qualifying_thirds(db, standings))
        if len(thirds) != 8:
            raise RuntimeError(f"Expected 8 qualifying thirds, got {len(thirds)}: {thirds}")

        bracket = load_bracket()
        key = "".join(thirds)
        third_assignment = bracket["third_table"].get(key)
        if not third_assignment:
            raise RuntimeError(f"No Annex C row for thirds combination {key!r}")

        if verbose:
            print(f"Standings final, thirds={thirds}, Annex C key={key}")
            print(f"Third-place R32 slot assignment: {third_assignment}")

        for fx in R32_FIXTURES:
            home_code = _resolve_slot(fx["home_slot"], standings, third_assignment)
            away_code = _resolve_slot(fx["away_slot"], standings, third_assignment)
            if not home_code or not away_code:
                summary["skipped"].append({"id": fx["id"], "reason": "unresolved-slot",
                                           "home_slot": fx["home_slot"], "away_slot": fx["away_slot"]})
                if verbose:
                    print(f"  SKIP {fx['id']}: cannot resolve {fx['home_slot']}/{fx['away_slot']}")
                continue
            if not db.get(Team, home_code) or not db.get(Team, away_code):
                summary["skipped"].append({"id": fx["id"], "reason": "unknown-team",
                                           "home_code": home_code, "away_code": away_code})
                continue

            kickoff = datetime.fromisoformat(fx["kickoff"])
            existing = db.get(Match, fx["id"])
            if not existing:
                db.add(Match(
                    id=fx["id"],
                    group=None,           # knockouts have no group
                    matchday=fx["matchday"],
                    kickoff=kickoff,
                    venue=fx["venue"],
                    home_code=home_code,
                    away_code=away_code,
                    status="upcoming",
                ))
                summary["inserted"] += 1
                action = "INSERT"
            else:
                # Only update fields that are safe to mutate. Never touch score
                # or status once a match has progressed past "upcoming".
                if existing.status == "upcoming":
                    existing.matchday = fx["matchday"]
                    existing.kickoff = kickoff
                    existing.venue = fx["venue"]
                    existing.home_code = home_code
                    existing.away_code = away_code
                    summary["updated"] += 1
                    action = "UPDATE"
                else:
                    action = f"KEEP({existing.status})"
            summary["matches"].append({"id": fx["id"], "action": action,
                                       "home": home_code, "away": away_code,
                                       "kickoff": fx["kickoff"], "venue": fx["venue"]})
            if verbose:
                print(f"  {action} {fx['id']}: {home_code} vs {away_code}  ({fx['venue']})")

        db.commit()
        if verbose:
            print(f"\nDone. Inserted={summary['inserted']} Updated={summary['updated']} Skipped={len(summary['skipped'])}")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    seed_r32(verbose=True)
