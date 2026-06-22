"""Importer for the WC2026 per-90 player-stats open dataset.

Source: risingtransfers/world-cup-2026-data  (data/per90_stats.csv), CC BY 4.0.
  Attribution: Per-90 stats — Rising Transfers (risingtransfers.com), CC BY 4.0.

1,181 WC players with 2025-26 per-90 metrics (min 450 league minutes). Surfaced
on the team + player pages so squads show REAL club-season output (goals/xG-proxy/
assists/key passes per 90) instead of only the 2-3 WC games.

JOIN KEY: the dataset's `player_id` is the RISINGTRANSFERS id, not api-football's,
so we cannot join on id. We join to our PlayerProfile by a NORMALISED NAME
(accent-stripped, lowercased, punctuation-collapsed), with the slug kept as a
secondary disambiguator. normalise_name() is the contract that makes that work.
"""
from __future__ import annotations

import csv
import re
import unicodedata


def normalise_name(name: str) -> str:
    """Lowercase, strip accents, drop punctuation, collapse whitespace.

    "Éder Militão" -> "eder militao"; "O'Brien" -> "obrien". Used as the join
    key between our PlayerProfile.name and the dataset's player_name so accent /
    punctuation spelling differences don't break the match.
    """
    if not name:
        return ""
    # Decompose accents and drop the combining marks.
    decomposed = unicodedata.normalize("NFKD", name)
    ascii_name = "".join(c for c in decomposed if not unicodedata.combining(c))
    ascii_name = ascii_name.lower()
    # Keep letters, digits and spaces; drop everything else (apostrophes, dots…).
    ascii_name = re.sub(r"[^a-z0-9\s]", "", ascii_name)
    return re.sub(r"\s+", " ", ascii_name).strip()


def _to_int(v) -> int:
    try:
        return int(float(v))
    except (ValueError, TypeError):
        return 0


def _to_float(v):
    s = (v or "").strip() if isinstance(v, str) else v
    if s in (None, ""):
        return None
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


_FLOAT_FIELDS = (
    "goals_per90", "assists_per90", "shots_per90", "key_passes_per90",
    "tackles_per90", "interceptions_per90", "clearances_per90", "passes_per90",
    "pass_accuracy_pct", "saves_per90", "rating",
)


def parse_per90(csv_path: str) -> list[dict]:
    """Parse the per-90 CSV into a list of normalised dicts ready to upsert.

    Each dict carries the dataset name + slug + the `name_key` join key plus the
    per-90 metrics. Numeric fields that fail to parse become None (or 0 for
    minutes), so a stray bad cell never drops the whole player.
    """
    out: list[dict] = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = (row.get("player_name") or "").strip()
            if not name:
                continue
            rec = {
                "name": name,
                "name_key": normalise_name(name),
                "slug": (row.get("slug") or "").strip(),
                "season": (row.get("season") or "").strip(),
                "minutes": _to_int(row.get("minutes")),
            }
            for field in _FLOAT_FIELDS:
                rec[field] = _to_float(row.get(field))
            out.append(rec)
    return out


# --- in-memory lookup (loaded once at startup) ------------------------------
# We keep the per-90 stats as a name-keyed dict in memory rather than a DB table:
# it's read-only reference data joined by name, so a table + SQL join would be
# overkill (YAGNI). squad-rich looks players up by normalise_name(profile.name).

import os as _os  # noqa: E402
import logging as _logging  # noqa: E402

_logger = _logging.getLogger(__name__)

_BUNDLED_CSV = _os.path.join(
    _os.path.dirname(_os.path.dirname(__file__)), "datasets", "wc2026_per90.csv"
)

# name_key -> per-90 record. Empty until ensure_per90_loaded() runs.
_PER90_BY_NAME: dict[str, dict] = {}


def ensure_per90_loaded() -> int:
    """Load the bundled per-90 dataset into the in-memory name lookup once.

    No-ops if already loaded. Returns the number of players in the lookup.
    Safe on every boot; falls back to an empty lookup (no per-90 shown) if the
    file is missing or unparseable.
    """
    if _PER90_BY_NAME:
        return len(_PER90_BY_NAME)
    if not _os.path.exists(_BUNDLED_CSV):
        _logger.warning("bundled per-90 dataset not found at %s", _BUNDLED_CSV)
        return 0
    try:
        rows = parse_per90(_BUNDLED_CSV)
    except Exception as exc:
        _logger.warning("per-90 import failed (%s); no per-90 stats shown", exc)
        return 0
    for r in rows:
        # Last write wins on a name clash; the dataset has one row per player.
        if r["name_key"]:
            _PER90_BY_NAME[r["name_key"]] = r
    _logger.info("per-90 stats loaded: %d players (Rising Transfers CC BY 4.0)", len(_PER90_BY_NAME))
    return len(_PER90_BY_NAME)


def get_per90_for_name(name: str) -> dict | None:
    """Look up a player's per-90 record by display name (normalised). None if
    we have no per-90 row for that player."""
    if not _PER90_BY_NAME:
        ensure_per90_loaded()
    return _PER90_BY_NAME.get(normalise_name(name))
