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
