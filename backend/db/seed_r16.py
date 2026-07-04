"""Seed the WC2026 Round of 16 fixtures (matchday 5, M089-M096).

Resolves each tie from R32 winners per the wc2026_bracket.json tree
(M089 = W74 v W77, M090 = W73 v W75, ...). Winner of a completed knockout
match = higher aggregate score, or higher shootout score when the aggregate
is level (M074/M075/M088 all went to pens this round).

Kickoffs are UTC from api-football's league-1 fixture list (fetched
2026-07-04, cross-checked against ESPN/NBC published ET times); venues from
the same list, with the three the API hadn't filled yet (M093/M095/M096)
verified against the FIFA schedule as carried by ESPN + NBC + Yahoo.
Pairings were verified against api-football's own R16 fixtures before this
file was written — all 8 matched the tree-derived winners.

Run: `python -m backend.db.seed_r16`
Idempotent: re-running updates kickoff/venue/teams while a fixture is still
"upcoming" but never touches a row whose status has advanced.
"""
from __future__ import annotations

from datetime import datetime

from backend.db.session import init_db, SessionLocal
from backend.db.models import Match, Team


# Official R16 fixtures. Winner-feed slots ("W074") reference the R32 match
# whose winner fills the slot — resolved from our Match rows at seed time.
R16_FIXTURES: list[dict] = [
    {"id": "M089", "matchday": 5, "kickoff": "2026-07-04T21:00:00",
     "venue": "Lincoln Financial Field, Philadelphia", "home_feed": "M074", "away_feed": "M077"},
    {"id": "M090", "matchday": 5, "kickoff": "2026-07-04T17:00:00",
     "venue": "NRG Stadium, Houston",                  "home_feed": "M073", "away_feed": "M075"},
    {"id": "M091", "matchday": 5, "kickoff": "2026-07-05T20:00:00",
     "venue": "MetLife Stadium, New York",             "home_feed": "M076", "away_feed": "M078"},
    {"id": "M092", "matchday": 5, "kickoff": "2026-07-06T00:00:00",
     "venue": "Estadio Azteca, Mexico City",           "home_feed": "M079", "away_feed": "M080"},
    {"id": "M093", "matchday": 5, "kickoff": "2026-07-06T19:00:00",
     "venue": "AT&T Stadium, Dallas",                  "home_feed": "M083", "away_feed": "M084"},
    {"id": "M094", "matchday": 5, "kickoff": "2026-07-07T00:00:00",
     "venue": "Lumen Field, Seattle",                  "home_feed": "M081", "away_feed": "M082"},
    {"id": "M095", "matchday": 5, "kickoff": "2026-07-07T16:00:00",
     "venue": "Mercedes-Benz Stadium, Atlanta",        "home_feed": "M086", "away_feed": "M088"},
    {"id": "M096", "matchday": 5, "kickoff": "2026-07-07T20:00:00",
     "venue": "BC Place, Vancouver",                   "home_feed": "M085", "away_feed": "M087"},
]


def _winner(db, match_id: str) -> str | None:
    """Winner of a completed knockout match, shootout-aware.

    Aggregate score decides (covers regulation + AET wins); a level aggregate
    means it went to pens, so the shootout score decides. Returns None when
    the match isn't complete or the result is unresolvable (which would mean
    corrupt data — a knockout can't end without a winner).
    """
    m = db.get(Match, match_id)
    if not m or m.status != "complete" or m.home_score is None or m.away_score is None:
        return None
    if m.home_score > m.away_score:
        return m.home_code
    if m.away_score > m.home_score:
        return m.away_code
    if m.shootout_home_score is None or m.shootout_away_score is None:
        return None
    if m.shootout_home_score > m.shootout_away_score:
        return m.home_code
    if m.shootout_away_score > m.shootout_home_score:
        return m.away_code
    return None


def seed_r16(verbose: bool = True) -> dict:
    """Insert/update the 8 R16 fixtures. Returns a summary dict."""
    init_db()
    db = SessionLocal()
    summary = {"inserted": 0, "updated": 0, "skipped": [], "matches": []}
    try:
        for fx in R16_FIXTURES:
            home_code = _winner(db, fx["home_feed"])
            away_code = _winner(db, fx["away_feed"])
            if not home_code or not away_code:
                summary["skipped"].append({"id": fx["id"], "reason": "unresolved-winner",
                                           "home_feed": fx["home_feed"], "away_feed": fx["away_feed"]})
                if verbose:
                    print(f"  SKIP {fx['id']}: winner unresolved for {fx['home_feed']}/{fx['away_feed']}")
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
    seed_r16(verbose=True)
