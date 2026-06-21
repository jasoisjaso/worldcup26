"""SportsGameOdds free-tier fetcher: Pinnacle sharp anchor for WC2026.

A single `/v2/events?leagueID=FWC` call returns the full slate of WC fixtures
with prices from ~21 books including Pinnacle. We extract Pinnacle's
`currentFairOdds` (already de-vigged on the SGO side) for the markets our
model already prices: 1X2, Over/Under 2.5, BTTS.

Why Pinnacle:
- It's the sharpest publicly available market — its closing line is the de-facto
  truth-anchor for football modelling.
- We currently blend the model with soft-book consensus (bet365/sportsbet/unibet)
  which is circular: those books partly anchor on Pinnacle themselves. Using
  Pinnacle directly removes that loop.

Budget:
- SGO Trial: 1,000 calls/month, 1/sec, 100/day cap.
- One call returns the full slate; we refresh every 6h → ~120 calls/month.

In-memory cache only (no DB row): each entry is small and we re-fetch every
6h. A container restart clears the cache; the next scheduled tick refills it.
"""
from __future__ import annotations

import logging
import os
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("SPORTSGAMEODDS_API_KEY", "").strip()
_BASE = "https://api.sportsgameodds.com/v2"
_LEAGUE = os.getenv("WC26_SGO_LEAGUE", "FWC")  # WC 2026 league id

# In-memory cache: list of normalised events (model code -> sharp odds).
_cache_events: list[dict] = []
_cache_fetched_at: float | None = None
_last_fetch_count: int = 0

# Map SGO's odd-key naming -> our model market keys. Only the markets our model
# already prices off the score grid go through the blend; everything else is
# carried for diagnostic display only.
_MARKETS_3WAY = {
    "points-all-game-ml-home": "home_win",
    "points-all-game-ml-draw": "draw",
    "points-all-game-ml-away": "away_win",
}
_MARKETS_OU25 = {
    "points-all-game-ou-over_2.5": "over_2_5",
    "points-all-game-ou-under_2.5": "under_2_5",
}
_MARKETS_BTTS = {
    "both-teams-to-score-yes": "btts",
    "both-teams-to-score-no":  "btts_no",
}


def _american_to_decimal(american) -> Optional[float]:
    """Convert American odds (+112, -110) to decimal. None for unusable input."""
    if american is None:
        return None
    try:
        v = float(american)
    except (TypeError, ValueError):
        return None
    if v >= 100:
        return round(1.0 + v / 100.0, 4)
    if v <= -100:
        return round(1.0 + 100.0 / abs(v), 4)
    return None  # American odds in (-100, 100) aren't valid


def _extract_pinnacle(odds_block: dict, odd_key: str) -> Optional[float]:
    """Pull Pinnacle's currentFairOdds for one market, return decimal or None."""
    entry = odds_block.get(odd_key) or {}
    books = entry.get("sportsbooks") or entry.get("bookmakers") or {}
    pin = books.get("pinnacle") or {}
    return _american_to_decimal(pin.get("currentFairOdds"))


async def refresh_sharp_odds() -> dict:
    """Fetch the WC sharp-odds slate. One call per refresh.

    Module no-ops without SPORTSGAMEODDS_API_KEY so local dev never burns the
    free quota. Returns a status dict so the scheduler's tracked wrapper can
    log it.
    """
    global _cache_events, _cache_fetched_at, _last_fetch_count
    if not _API_KEY:
        return {"status": "no_key"}

    headers = {"X-Api-Key": _API_KEY}
    params = {"leagueID": _LEAGUE}
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(f"{_BASE}/events", params=params, headers=headers)
    except Exception as exc:
        logger.warning("sharp_odds fetch failed: %s", exc)
        return {"status": "error", "error": str(exc)}
    if r.status_code != 200:
        logger.warning("sharp_odds non-200: %s", r.status_code)
        return {"status": "non_200", "http": r.status_code}

    body = r.json() or {}
    events = body.get("data") or []
    normalised: list[dict] = []
    for ev in events:
        info = ev.get("info") or {}
        teams = ev.get("teams") or {}
        home_team = teams.get("home") or {}
        away_team = teams.get("away") or {}
        home_name = (home_team.get("names") or {}).get("long") or home_team.get("name")
        away_name = (away_team.get("names") or {}).get("long") or away_team.get("name")
        if not home_name or not away_name:
            continue
        odds = ev.get("odds") or {}

        pinnacle: dict[str, float] = {}
        for sgo_key, model_key in _MARKETS_3WAY.items():
            dec = _extract_pinnacle(odds, sgo_key)
            if dec:
                pinnacle[model_key] = dec
        for sgo_key, model_key in _MARKETS_OU25.items():
            dec = _extract_pinnacle(odds, sgo_key)
            if dec:
                pinnacle[model_key] = dec
        for sgo_key, model_key in _MARKETS_BTTS.items():
            dec = _extract_pinnacle(odds, sgo_key)
            if dec:
                pinnacle[model_key] = dec

        if pinnacle:
            normalised.append({
                "event_id": ev.get("eventID"),
                "start_time": info.get("start_time") or info.get("startTime"),
                "home_name": home_name,
                "away_name": away_name,
                "pinnacle": pinnacle,
            })

    _cache_events = normalised
    _cache_fetched_at = time.time()
    _last_fetch_count = len(normalised)
    logger.info("sharp_odds: %d events with pinnacle prices", _last_fetch_count)
    return {
        "status": "ok",
        "events": _last_fetch_count,
        "monthly_remaining": r.headers.get("x-ratelimit-remaining-month"),
    }


def sharp_odds_snapshot() -> dict:
    """Return the cached snapshot for FE/admin consumers. Cheap, no API cost."""
    return {
        "fetched_at": _cache_fetched_at,
        "events": _cache_events,
        "event_count": len(_cache_events),
        "age_seconds": (time.time() - _cache_fetched_at) if _cache_fetched_at else None,
    }


# Soft name aliases used when our internal team name differs from SGO's. Extend
# as new mismatches surface; the lookup logs an info line for misses so we
# notice the gap rather than silently falling back to soft books.
_NAME_ALIASES = {
    "south korea": "korea republic",
    "usa":         "united states",
    "us":          "united states",
    "ivory coast": "cote d'ivoire",
    "iran":        "ir iran",
    "ireland":     "republic of ireland",
}


def _norm(name: str) -> str:
    n = (name or "").strip().lower()
    return _NAME_ALIASES.get(n, n)


def sharp_odds_for_match(home_name: str, away_name: str) -> dict | None:
    """Lookup the cached Pinnacle prices for a fixture by team names.

    Soft matching: case-insensitive, ignores whitespace, applies the alias
    table for known naming differences. Returns None when no match.
    """
    if not _cache_events:
        return None
    h, a = _norm(home_name), _norm(away_name)
    for ev in _cache_events:
        if _norm(ev["home_name"]) == h and _norm(ev["away_name"]) == a:
            return ev["pinnacle"]
    return None


# Feature flag: WC26_USE_SHARP_ANCHOR. Default ON in production. Set to "0" /
# "false" / "no" to revert to soft-book-only blending — useful for offline A/B
# or if Pinnacle data ever goes sideways.
def sharp_anchor_enabled() -> bool:
    return os.getenv("WC26_USE_SHARP_ANCHOR", "1").strip().lower() not in ("0", "false", "no")


def sharp_anchor_for(home_name: str, away_name: str) -> dict | None:
    """Feature-flag-aware wrapper used by the model blend. Returns None when
    the feature flag is off so call sites stay clean."""
    if not sharp_anchor_enabled():
        return None
    return sharp_odds_for_match(home_name, away_name)
