"""Seed the WC2026 3rd-place playoff (M103) and Final (M104) from semifinal results.

The bracket tree in wc2026_bracket.json defines:
  M103 (3rd place) = L101 v L102  (losers of the semifinals)
  M104 (Final)     = W101 v W102  (winners of the semifinals)

advance_knockout.py relies on api-football publishing these fixtures with
real teams filled in, but that feed can lag or fail. This module resolves
M103/M104 directly from our own completed semifinal Match rows — the same
self-contained pattern seed_r16.py uses for the Round of 16.

Run: `python -m backend.db.seed_finals`
Idempotent: inserts a new fixture or updates an existing one only while it
is still 'upcoming'; never touches a row that has advanced past 'upcoming'.
"""
from __future__ import annotations

from datetime import datetime

from backend.db.session import init_db, SessionLocal
from backend.db.models import Match, Team


# Official FIFA schedule for the final two fixtures. Kickoffs in UTC.
# M103 = 3rd place, M104 = Final. Venues from the FIFA schedule.
FINALS_FIXTURES: list[dict] = [
    {
        "id": "M103",
        "matchday": 8,
        "kickoff": "2026-07-18T19:00:00",
        "venue": "Hard Rock Stadium, Miami",
        "home_feed": "M101",   # L101 — loser of semifinal 1
        "away_feed": "M102",   # L102 — loser of semifinal 2
        "home_side": "loser",
        "away_side": "loser",
    },
    {
        "id": "M104",
        "matchday": 8,
        "kickoff": "2026-07-19T19:00:00",
        "venue": "MetLife Stadium, East Rutherford",
        "home_feed": "M101",   # W101 — winner of semifinal 1
        "away_feed": "M102",   # W102 — winner of semifinal 2
        "home_side": "winner",
        "away_side": "winner",
    },
]


def _winner(db, match_id: str) -> str | None:
    """Winner of a completed knockout match, shootout-aware."""
    m = db.get(Match, match_id)
    if not m or m.status != "complete" or m.home_score is None or m.away_score is None:
        return None
    if m.home_score > m.away_score:
        return m.home_code
    if m.away_score > m.home_score:
        return m.away_code
    # Level aggregate → shootout decides
    if m.shootout_home_score is None or m.shootout_away_score is None:
        return None
    if m.shootout_home_score > m.shootout_away_score:
        return m.home_code
    if m.shootout_away_score > m.shootout_home_score:
        return m.away_code
    return None


def _loser(db, match_id: str) -> str | None:
    """Loser of a completed knockout match, shootout-aware."""
    m = db.get(Match, match_id)
    if not m or m.status != "complete" or m.home_score is None or m.away_score is None:
        return None
    if m.home_score > m.away_score:
        return m.away_code
    if m.away_score > m.home_score:
        return m.home_code
    # Level aggregate → shootout decides
    if m.shootout_home_score is None or m.shootout_away_score is None:
        return None
    if m.shootout_home_score > m.shootout_away_score:
        return m.away_code
    if m.shootout_away_score > m.shootout_home_score:
        return m.home_code
    return None


def seed_finals(verbose: bool = True) -> dict:
    """Insert/update M103 (3rd place) and M104 (Final) from semifinal results.

    Returns a summary dict. No-op (returns early) if the semifinals haven't
    both completed yet.
    """
    init_db()
    db = SessionLocal()
    summary: dict = {"inserted": 0, "updated": 0, "kept": 0, "skipped": 0, "matches": []}
    try:
        for fx in FINALS_FIXTURES:
            if fx["home_side"] == "winner":
                home_code = _winner(db, fx["home_feed"])
            else:
                home_code = _loser(db, fx["home_feed"])

            if fx["away_side"] == "winner":
                away_code = _winner(db, fx["away_feed"])
            else:
                away_code = _loser(db, fx["away_feed"])

            if not home_code or not away_code:
                summary["skipped"] += 1
                if verbose:
                    print(f"  SKIP {fx['id']}: cannot resolve "
                          f"{'winner' if fx['home_side'] == 'winner' else 'loser'} of {fx['home_feed']}"
                          f" / {'winner' if fx['away_side'] == 'winner' else 'loser'} of {fx['away_feed']}")
                continue

            if not db.get(Team, home_code) or not db.get(Team, away_code):
                summary["skipped"] += 1
                if verbose:
                    print(f"  SKIP {fx['id']}: unknown team {home_code}/{away_code}")
                continue

            kickoff = datetime.fromisoformat(fx["kickoff"])
            existing = db.get(Match, fx["id"])

            if existing is None:
                db.add(Match(
                    id=fx["id"],
                    group=None,
                    matchday=fx["matchday"],
                    kickoff=kickoff,
                    venue=fx["venue"],
                    home_code=home_code,
                    away_code=away_code,
                    status="upcoming",
                ))
                summary["inserted"] += 1
                action = "INSERT"
            elif existing.status == "upcoming":
                existing.matchday = fx["matchday"]
                existing.kickoff = kickoff
                existing.venue = fx["venue"]
                existing.home_code = home_code
                existing.away_code = away_code
                summary["updated"] += 1
                action = "UPDATE"
            else:
                summary["kept"] += 1
                action = f"KEEP({existing.status})"

            summary["matches"].append({
                "id": fx["id"], "action": action,
                "home": home_code, "away": away_code,
                "kickoff": fx["kickoff"], "venue": fx["venue"],
            })
            if verbose:
                label = "3rd place" if fx["id"] == "M103" else "Final"
                print(f"  {action} {fx['id']} ({label}): {home_code} vs {away_code}  ({fx['venue']})")

        db.commit()
        if verbose:
            print(f"\nDone. inserted={summary['inserted']} updated={summary['updated']} "
                  f"kept={summary['kept']} skipped={summary['skipped']}")
        return summary
    finally:
        db.close()


if __name__ == "__main__":
    seed_finals(verbose=True)
