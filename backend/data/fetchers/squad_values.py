"""
Squad market values for all 48 WC2026 nations — drives a quality multiplier on
DC/ELO lambdas. The ratio of squad values captures current squad depth and star
power that historical goals data lags on.

Effect is deliberately small: ±8% max for a 10x value gap (e.g. England vs Haiti).
This preserves the DC model's calibration while adding a quality floor.

DATA SOURCE (2026-06-22): values come from the risingtransfers/world-cup-2026-data
open dataset (CC BY 4.0) — an AI transfer-value estimate per player, summed to a
total per nation. Attribution: Squad values — Rising Transfers (risingtransfers.com),
CC BY 4.0. This replaced a DEAD Transfermarkt scraper (the old refresh_squad_values
had a no-op parse loop, so the model silently ran on the frozen STATIC_VALUES
hand-table for the whole tournament). STATIC_VALUES is kept ONLY as the offline
fallback when the dataset hasn't been imported yet.

load_imported_squad_values(path) populates the live cache from the dataset CSV.
get_squad_quality_multipliers() uses that cache, falling back to STATIC_VALUES.
"""
from __future__ import annotations
import logging
import math
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Static fallback — approximate Transfermarkt squad values, millions EUR (2025-26)
STATIC_VALUES: dict[str, float] = {
    # UEFA
    "fr": 1200, "gb-eng": 1100, "br": 1100, "de": 935, "es": 950,
    "pt": 930, "be": 740, "nl": 720, "ch": 450, "at": 310,
    "no": 380, "tr": 290, "cz": 240, "se": 270, "hr": 390,
    "gb-sct": 180, "ba": 140,
    # CONMEBOL
    "ar": 890, "co": 520, "uy": 340, "ec": 220, "py": 140,
    # AFC
    "jp": 240, "kr": 260, "au": 145, "ir": 95,
    "sa": 100, "uz": 55, "qa": 70, "jo": 45, "iq": 65,
    # CONCACAF
    "us": 340, "ca": 220, "mx": 195, "pa": 55, "cw": 35, "ht": 30,
    # CAF
    "ma": 220, "sn": 230, "ci": 310, "eg": 150, "dz": 140,
    "tn": 90, "gh": 110, "za": 65, "cd": 60, "cv": 35,
    # OFC
    "nz": 40,
}

# Max lambda multiplier from squad value ratio (±8% at extreme end)
_SV_SCALE = 0.08
_SV_LOG_BASE = math.log(10)   # full ±8% at a 10x value gap

_cache: dict[str, float] = {}
_cache_built_at: Optional[datetime] = None


def _multipliers_from_values(home_val: float, away_val: float) -> tuple[float, float]:
    """
    Returns (home_mult, away_mult). The team with a higher squad value gets
    a slight boost; the lower-value team gets a slight penalty.
    Net effect at 2x gap: ~±5.5%. At 10x gap: ~±8%.
    """
    if home_val <= 0 or away_val <= 0:
        return 1.0, 1.0
    log_ratio = math.log(home_val / away_val)
    # Scale: _SV_SCALE * log_ratio / log(10) — normalised so 10x = ±_SV_SCALE
    adj = _SV_SCALE * log_ratio / _SV_LOG_BASE
    adj = max(-_SV_SCALE, min(_SV_SCALE, adj))
    return 1.0 + adj, 1.0 - adj


def get_squad_quality_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """
    Returns (home_mult, away_mult) based on squad market value ratio.
    Uses the imported dataset cache if available, falls back to STATIC_VALUES.
    """
    values = _cache if _cache else STATIC_VALUES
    home_val = values.get(home_code, 200.0)
    away_val = values.get(away_code, 200.0)
    return _multipliers_from_values(home_val, away_val)


def load_imported_squad_values(csv_path: str, min_nations: int = 20) -> int:
    """Load per-nation squad totals from the risingtransfers WC2026 squads CSV
    into the live cache. Returns the number of nations loaded.

    Replaces the old (dead) Transfermarkt scraper. The values are AI transfer-
    value estimates summed per nation, in millions EUR — same unit + scale as
    STATIC_VALUES, so the ±8% multiplier is unchanged. On any failure the cache
    is left as-is and get_squad_quality_multipliers() falls back to STATIC_VALUES.

    `min_nations` guards against a truncated/garbled file quietly replacing the
    table with junk; the real dataset has 48 nations.
    """
    global _cache, _cache_built_at
    try:
        from backend.data.importers.wc2026_squad_values import aggregate_values
        values = aggregate_values(csv_path)
    except Exception as exc:
        logger.warning("squad-value import failed (%s); keeping fallback", exc)
        return 0
    if len(values) < min_nations:
        logger.warning("squad-value import parsed only %d nations; ignoring", len(values))
        return 0
    _cache = values
    _cache_built_at = datetime.utcnow()
    logger.info("squad values imported: %d nations (Rising Transfers CC BY 4.0)", len(values))
    return len(values)


# Path to the bundled dataset CSV (ships in the Docker image so startup has no
# network dependency). risingtransfers/world-cup-2026-data, CC BY 4.0.
import os as _os  # noqa: E402
_BUNDLED_CSV = _os.path.join(
    _os.path.dirname(_os.path.dirname(__file__)), "datasets", "wc2026_squads.csv"
)


def ensure_squad_values_loaded() -> int:
    """Load the bundled WC2026 squad-value dataset into the cache once, at startup.

    No-ops (returns the current count) if already loaded. Safe to call on every
    boot. Returns the number of nations in the cache afterwards.
    """
    if _cache:
        return len(_cache)
    if _os.path.exists(_BUNDLED_CSV):
        return load_imported_squad_values(_BUNDLED_CSV)
    logger.warning("bundled squad-value dataset not found at %s; using STATIC_VALUES", _BUNDLED_CSV)
    return 0
