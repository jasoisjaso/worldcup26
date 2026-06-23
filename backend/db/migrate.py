"""Tiny additive migrations for the live SQLite DB.

SQLAlchemy's ``create_all`` creates missing tables but never alters existing ones, so new
columns on an already-deployed table need an explicit ``ALTER TABLE ... ADD COLUMN``. Every
migration here is purely additive (new nullable columns) and idempotent (guarded by a
column-existence check), so it can never drop or rewrite the production data — existing rows
simply get NULL for the new column. Run after ``init_db()`` and before ``seed()``."""
from __future__ import annotations

from sqlalchemy import inspect, text

from backend.db.session import engine

# table -> {column: SQL type}
_ADDITIVE_COLUMNS: dict[str, dict[str, str]] = {
    "predictions": {
        "closing_odds": "FLOAT",
        "clv": "FLOAT",
    },
    "harvest_raw": {
        "processed": "BOOLEAN DEFAULT 0",
    },
    "matches": {
        "home_ht_score": "INTEGER",
        "away_ht_score": "INTEGER",
        # Interruption lifecycle — see Match docstring. Lets a SUSP/INT/PST/
        # ABD/AWD fixture stop poisoning calibration + bet settlement.
        "interruption_status": "VARCHAR",
        "interruption_reason": "VARCHAR",
        "interruption_started_at": "DATETIME",
        "partial_home_score": "INTEGER",
        "partial_away_score": "INTEGER",
        # Penalty shootout tiebreaker score — see Match docstring. NULL for
        # every match that didn't go to pens; only populated for knockout
        # matches with status=PEN. home_score/away_score still show the
        # post-ET draw, the shootout score is the "(4-3 pens)" suffix.
        "shootout_home_score": "INTEGER",
        "shootout_away_score": "INTEGER",
    },
    "live_match_state": {
        # Mirror of Match.shootout_*_score for live readers — populated on
        # every tick during status="P", frozen at status="PEN".
        "shootout_home_score": "INTEGER",
        "shootout_away_score": "INTEGER",
    },
    "match_h2h": {
        "venue": "VARCHAR",
    },
    "fixture_archive": {
        "shots_off_target": "INTEGER",
        "shots_insidebox": "INTEGER",
        "shots_outsidebox": "INTEGER",
        "shots_blocked": "INTEGER",
        "offsides": "INTEGER",
        "goalkeeper_saves": "INTEGER",
        "goals_prevented": "FLOAT",
    },
    "player_tournament_stats": {
        # Spot-kick attempt tracking — see PlayerTournamentStats docstring.
        # Lets the player profile and the betting layer answer "how many
        # times has X actually stepped up" not just "how many did X score".
        "penalty_attempts": "INTEGER DEFAULT 0",
        "penalty_misses": "INTEGER DEFAULT 0",
        "shootout_penalty_goals": "INTEGER DEFAULT 0",
        "shootout_penalty_misses": "INTEGER DEFAULT 0",
    },
}


def run_migrations() -> None:
    insp = inspect(engine)
    existing_tables = set(insp.get_table_names())
    for table, columns in _ADDITIVE_COLUMNS.items():
        if table not in existing_tables:
            continue  # create_all will build it with the columns already present
        have = {c["name"] for c in insp.get_columns(table)}
        to_add = {name: typ for name, typ in columns.items() if name not in have}
        if not to_add:
            continue
        with engine.begin() as conn:
            for name, typ in to_add.items():
                conn.execute(text(f'ALTER TABLE {table} ADD COLUMN {name} {typ}'))
                print(f"[migrate] added {table}.{name} ({typ})")
