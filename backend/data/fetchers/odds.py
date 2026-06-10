"""Fetches live odds from The Odds API and caches them in memory.

Matches Odds API events to DB records by kickoff time + team name similarity.
Falls back silently if ODDS_API_KEY is not set or sport not yet listed.
"""
import asyncio
import difflib
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy.orm import aliased

from backend.db.models import Match, Team
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
SPORT_KEY = "soccer_fifa_world_cup"
BASE_URL = "https://api.the-odds-api.com/v4"
CACHE_TTL = timedelta(hours=4)
KICKOFF_WINDOW_SECS = 3600  # 60 minutes — wider window, team names do the tiebreaking

_odds_by_match: dict[str, dict[str, float]] = {}
_cached_at: datetime | None = None
_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


def _name_score(api_name: str, db_name: str) -> float:
    a = api_name.lower().strip()
    b = db_name.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


def _extract_best_odds(event: dict, swap_home_away: bool = False) -> dict[str, float]:
    home_name = event.get("home_team", "")
    away_name = event.get("away_team", "")
    collected: dict[str, list[float]] = {}

    for bm in event.get("bookmakers", []):
        for market in bm.get("markets", []):
            mkey = market["key"]
            for outcome in market["outcomes"]:
                name = outcome["name"]
                price = float(outcome["price"])

                if mkey == "h2h":
                    if name == home_name:
                        key = "away_win" if swap_home_away else "home_win"
                    elif name.lower() == "draw":
                        key = "draw"
                    elif name == away_name:
                        key = "home_win" if swap_home_away else "away_win"
                    else:
                        continue
                elif mkey == "totals":
                    if abs(outcome.get("point", 0) - 2.5) > 0.01:
                        continue
                    key = "over_2_5" if name.lower() == "over" else "under_2_5"
                else:
                    continue

                collected.setdefault(key, []).append(price)

    # Use median price across bookmakers — more realistic than best-available
    result: dict[str, float] = {}
    for key, prices in collected.items():
        prices_sorted = sorted(prices)
        n = len(prices_sorted)
        result[key] = prices_sorted[n // 2]
    return result


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
            HomeTeam = aliased(Team)
            AwayTeam = aliased(Team)
            match_rows = (
                db.query(Match.id, Match.kickoff, HomeTeam.name, AwayTeam.name)
                .join(HomeTeam, HomeTeam.code == Match.home_code)
                .join(AwayTeam, AwayTeam.code == Match.away_code)
                .filter(Match.status == "upcoming")
                .all()
            )
        finally:
            db.close()

        kickoff_index: list[tuple[datetime, str, str, str]] = []
        for match_id, kickoff, home_name, away_name in match_rows:
            if kickoff is None:
                continue
            kt = kickoff if kickoff.tzinfo else kickoff.replace(tzinfo=timezone.utc)
            kickoff_index.append((kt, match_id, home_name or "", away_name or ""))

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                resp = await client.get(
                    f"{BASE_URL}/sports/{SPORT_KEY}/odds",
                    params={
                        "apiKey": ODDS_API_KEY,
                        "regions": "uk,au",
                        "markets": "h2h,totals",
                        "oddsFormat": "decimal",
                        "bookmakers": "bet365,sportsbet,unibet",
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
        used_match_ids: set[str] = set()

        for event in events:
            commence_str = event.get("commence_time", "")
            try:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            except Exception:
                continue

            event_home = event.get("home_team", "")
            event_away = event.get("away_team", "")

            # Candidates: DB matches within the kickoff window
            candidates = [
                (kt, mid, hname, aname)
                for kt, mid, hname, aname in kickoff_index
                if abs((kt - commence_dt).total_seconds()) <= KICKOFF_WINDOW_SECS
                and mid not in used_match_ids
            ]

            if not candidates:
                continue

            # Score each candidate by team name similarity
            best_mid: str | None = None
            best_score = 0.0
            best_swapped = False

            for _, mid, hname, aname in candidates:
                score_normal = (
                    _name_score(event_home, hname) + _name_score(event_away, aname)
                ) / 2.0
                score_swapped = (
                    _name_score(event_home, aname) + _name_score(event_away, hname)
                ) / 2.0

                if score_normal >= score_swapped and score_normal > best_score:
                    best_score = score_normal
                    best_mid = mid
                    best_swapped = False
                elif score_swapped > score_normal and score_swapped > best_score:
                    best_score = score_swapped
                    best_mid = mid
                    best_swapped = True

            if best_mid is None or best_score < 0.4:
                logger.debug(
                    "No confident match for %s vs %s (best score %.2f)",
                    event_home, event_away, best_score,
                )
                continue

            odds = _extract_best_odds(event, swap_home_away=best_swapped)
            if odds:
                new_cache[best_mid] = odds
                used_match_ids.add(best_mid)
                logger.debug(
                    "Matched %s vs %s -> %s (score=%.2f swapped=%s)",
                    event_home, event_away, best_mid, best_score, best_swapped,
                )

        _odds_by_match = new_cache
        _cached_at = now
        logger.info("Odds cache updated: %d matches with live odds", len(new_cache))


async def get_odds_for_match(match_id: str) -> dict[str, float]:
    """Return best bookmaker odds for this match. Triggers cache refresh if empty."""
    if not _odds_by_match and ODDS_API_KEY:
        await refresh_odds_cache()
    return _odds_by_match.get(match_id, {})
