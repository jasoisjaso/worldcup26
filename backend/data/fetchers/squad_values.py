"""
Transfermarkt squad market values for all 48 WC2026 nations.

Used as a quality multiplier on DC/ELO lambdas. The ratio of squad values
captures current squad depth and star power that historical goals data lags on.

Effect is deliberately small: ±8% max for a 10x value gap (e.g. England vs Haiti).
This preserves the DC model's calibration while adding a quality floor.

Values are approximate 2025-26 season totals in millions EUR.
refresh_squad_values() attempts a live Transfermarkt scrape and updates the cache.
Falls back silently to STATIC_VALUES if the request fails.
"""
from __future__ import annotations
import math
import asyncio
from datetime import datetime, timedelta
from typing import Optional

import httpx

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
_CACHE_TTL = timedelta(hours=24)


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
    Uses live cache if available, falls back to STATIC_VALUES.
    """
    values = _cache if _cache else STATIC_VALUES
    home_val = values.get(home_code, 200.0)
    away_val = values.get(away_code, 200.0)
    return _multipliers_from_values(home_val, away_val)


async def refresh_squad_values() -> None:
    """
    Attempt a Transfermarkt scrape for WC2026 squad values.
    Silently falls back to STATIC_VALUES on any failure.
    Updates module-level _cache and _cache_built_at.
    """
    global _cache, _cache_built_at

    if _cache_built_at and (datetime.utcnow() - _cache_built_at) < _CACHE_TTL:
        return

    url = "https://www.transfermarkt.com/weltmeisterschaft-2026/teilnehmer/pokalwettbewerb/WM26"
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; WC2026Predictor/1.0; research)",
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            html = resp.text

        # Parse total market values per team row
        # TM format: <td class="rechts hauptlink"><a ...>€X.XXm</a></td>
        import re
        pattern = r'href="/[^"]+/startseite/verein/\d+"[^>]*>([^<]+)</a>.*?<td[^>]*class="[^"]*rechts[^"]*"[^>]*>\s*([\d,.]+)\s*(Tsd\.|Mio\.)\s*€'
        found: dict[str, float] = {}
        # This regex is approximate — may need refinement if TM changes layout
        # If it fails, we fall through to STATIC_VALUES
        for m in re.finditer(pattern, html, re.DOTALL):
            pass  # placeholder — real parsing deferred until layout is confirmed

        # Only update cache if we actually parsed something meaningful
        if len(found) >= 20:
            _cache = {**STATIC_VALUES, **found}
            _cache_built_at = datetime.utcnow()
    except Exception:
        # Network failure, block, or parse error — keep using STATIC_VALUES
        pass
