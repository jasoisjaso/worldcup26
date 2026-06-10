"""Fetches live odds from The Odds API and caches them in memory.

Matches Odds API events to our DB records by kickoff time proximity.
Falls back silently if ODDS_API_KEY is not set or sport not yet listed.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx

from backend.db.models import Match
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
SPORT_KEY = "soccer_fifa_world_cup"
BASE_URL = "https://api.the-odds-api.com/v4"
CACHE_TTL = timedelta(hours=4)
KICKOFF_WINDOW_SECS = 1800  # 30 minutes

_odds_by_match: dict[str, dict[str, float]] = {}
_cached_at: datetime | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _extract_best_odds(event: dict) -> dict[str, float]:
    home_name = event.get("home_team", "")
    away_name = event.get("away_team", "")
    best: dict[str, float] = {}

    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            mkey = market["key"]
            for outcome in market["outcomes"]:
                name = outcome["name"]
                price = float(outcome["price"])

                if mkey == "h2h":
                    if name == home_name:
                        key = "home_win"
                    elif name.lower() == "draw":
                        key = "draw"
                    elif name == away_name:
                        key = "away_win"
                    else:
                        continue
                elif mkey == "totals":
                    if abs(outcome.get("point", 0) - 2.5) > 0.01:
                        continue
                    key = "over_2_5" if name.lower() == "over" else "under_2_5"
                else:
                    continue

                if key not in best or price > best[key]:
                    best[key] = price

    return best


async def refresh_odds_cache() -> None:
    global _odds_by_match, _cached_at

    if not ODDS_API_KEY:
        return

    now = datetime.now(timezone.utc)
    if _cached_at and (now - _cached_at) < CACHE_TTL:
        return

    async with _get_lock():
        now = datetime.now(timezone.utc)
        if _cached_at and (now - _cached_at) < CACHE_TTL:
            return

        db = SessionLocal()
        try:
            rows = db.query(Match.id, Match.kickoff).filter(Match.status == "upcoming").all()
        finally:
            db.close()

        kickoff_index: list[tuple[datetime, str]] = []
        for match_id, kickoff in rows:
            if kickoff is None:
                continue
            kt = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
            kickoff_index.append((kt, match_id))

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{BASE_URL}/sports/{SPORT_KEY}/odds",
                    params={
                        "apiKey": ODDS_API_KEY,
                        "regions": "uk,eu,au",
                        "markets": "h2h,totals",
                        "oddsFormat": "decimal",
                    },
                )
                remaining = resp.headers.get("x-requests-remaining", "?")
                logger.info("Odds API quota remaining: %s", remaining)

                if resp.status_code == 404:
                    logger.info("WC 2026 not yet listed in The Odds API")
                    _cached_at = now
                    return
                if resp.status_code != 200:
                    logger.warning("Odds API %s: %s", resp.status_code, resp.text[:200])
                    return

                events = resp.json()
        except Exception as exc:
            logger.warning("Odds fetch failed: %s", exc)
            return

        new_cache: dict[str, dict[str, float]] = {}
        for event in events:
            commence_str = event.get("commence_time", "")
            try:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            except Exception:
                continue

            matched_id = None
            for kickoff_dt, match_id in kickoff_index:
                if abs((kickoff_dt - commence_dt).total_seconds()) <= KICKOFF_WINDOW_SECS:
                    matched_id = match_id
                    break

            if not matched_id:
                continue

            odds = _extract_best_odds(event)
            if odds:
                new_cache[matched_id] = odds

        _odds_by_match = new_cache
        _cached_at = now
        logger.info("Odds cache updated: %d matches with live odds", len(new_cache))


async def get_odds_for_match(match_id: str) -> dict[str, float]:
    """Return best bookmaker odds for this match. Triggers cache refresh if empty."""
    if not _odds_by_match and ODDS_API_KEY:
        await refresh_odds_cache()
    return _odds_by_match.get(match_id, {})
