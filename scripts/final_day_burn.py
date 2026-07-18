"""Last pro-tier day (2026-07-18): bank player-level data for the EPL pivot.

Enqueues, per (team, season) found in team_season_standings:
  /players?team&season&page for pages 1..3  (season stat lines, ~40 players/team)
plus per distinct team:
  /transfers?team   (squad churn history)
  /players/squads?team  (current squad index)

Dedup in enqueue() makes this idempotent. Priority 300 keeps it below the
seeded 150-170 jobs so anything match-critical drains first. Run inside the
wc26-backend container:  python /app/scripts/final_day_burn.py
"""
from backend.data.harvester import enqueue
from backend.db.session import SessionLocal
from sqlalchemy import text

PLAYER_PAGES = 3

def main() -> None:
    db = SessionLocal()
    try:
        team_seasons = db.execute(text(
            "SELECT DISTINCT team_api_id, season FROM team_season_profiles"
        )).fetchall()
        teams = sorted({t for t, _ in team_seasons})
    finally:
        db.close()

    added = skipped = 0
    for team_id, season in team_seasons:
        for page in range(1, PLAYER_PAGES + 1):
            ok = enqueue(
                endpoint="/players",
                params={"team": team_id, "season": season, "page": page},
                priority=300,
            )
            added, skipped = (added + 1, skipped) if ok else (added, skipped + 1)

    for team_id in teams:
        for endpoint, params in (
            ("/transfers", {"team": team_id}),
            ("/players/squads", {"team": team_id}),
        ):
            ok = enqueue(endpoint=endpoint, params=params, priority=310)
            added, skipped = (added + 1, skipped) if ok else (added, skipped + 1)

    print(f"team_seasons={len(team_seasons)} teams={len(teams)} "
          f"added={added} skipped={skipped}")

if __name__ == "__main__":
    main()
