"""Load external forecaster predictions into the comparison tables.

Currently:
  * Opta tournament-level predictions from a hand-curated JSON file (per-team title %,
    round-by-round advance %, group winner %). Sourced from theanalyst.com and refreshed
    on demand. The file is committed so the comparison is auditable.

To add a new forecaster, drop a JSON file in this directory matching the same shape and
add a load_<forecaster>() function.
"""
from __future__ import annotations

import json
import os
from datetime import datetime

from sqlalchemy.orm import Session

from backend.db.models import CompetitorTournamentPrediction


_OPTA_FILE = os.path.join(os.path.dirname(__file__), "opta_pretournament.json")


def load_opta_tournament(db: Session) -> dict:
    """Upsert Opta's pre-tournament per-team round/title probabilities.

    Idempotent — re-running just overwrites previous values for the same forecaster.
    Returns a tiny summary {teams_loaded, source_url}.
    """
    with open(_OPTA_FILE, "r") as f:
        data = json.load(f)

    meta = data.get("_meta", {})
    source_url = meta.get("source_url")
    captured_at = meta.get("captured_at")

    count = 0
    for team_code, row in data.get("teams", {}).items():
        existing = (
            db.query(CompetitorTournamentPrediction)
            .filter(CompetitorTournamentPrediction.forecaster == "opta")
            .filter(CompetitorTournamentPrediction.team_code == team_code)
            .first()
        )
        if existing is None:
            existing = CompetitorTournamentPrediction(forecaster="opta", team_code=team_code)
            db.add(existing)
        existing.team_name = row.get("name")
        existing.p_title = row.get("p_title")
        existing.p_final = row.get("p_final")
        existing.p_semi = row.get("p_semi")
        existing.p_quarter = row.get("p_quarter")
        existing.p_r16 = row.get("p_r16")
        existing.p_r32 = row.get("p_r32")
        existing.p_first = row.get("p_first")
        existing.p_advance = row.get("p_advance")
        existing.source_url = source_url
        existing.captured_at = captured_at
        existing.snapshotted_at = datetime.utcnow()
        count += 1

    db.commit()
    return {"teams_loaded": count, "source_url": source_url, "captured_at": captured_at}
