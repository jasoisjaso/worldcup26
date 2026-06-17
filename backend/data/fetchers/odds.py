"""Fetches live odds from The Odds API and caches them in memory.

Matches Odds API events to DB records by kickoff time + team name similarity.
Falls back silently if ODDS_API_KEY is not set or the sport is not yet listed.

Per-book prices are kept (not just the median) so the value board can show the BEST
available price per outcome and which bookmaker offers it (line-shopping), and flag the
rare cross-book arbitrage. The model path still reads the median line, which keeps the
de-vig coherent.
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

# Flat median line per match {match_id: {market: price}} — the model/EV path reads this.
_odds_by_match: dict[str, dict[str, float]] = {}
# Per-book prices {match_id: {market: {book: {"price","point","last_update"}}}} — value board.
_book_odds: dict[str, dict[str, dict[str, dict]]] = {}
_cached_at: datetime | None = None
_lock: asyncio.Lock | None = None
# Last known remaining quota from the Odds API (x-requests-remaining), surfaced at /health.
_quota_remaining: int | None = None
# Below this, the value board and CLV capture are about to go dark mid-tournament.
_QUOTA_FLOOR = 25

# Rolling snapshots for steam detection: list of (timestamp, full odds_by_match copy)
_MAX_SNAPSHOTS = 6
_STEAM_SNAPSHOTS: list[tuple[datetime, dict[str, dict[str, float]]]] = []
_STEAM_THRESHOLD = 0.07   # 7 percentage point move in implied prob = steam signal


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


def _median(prices: list[float]) -> float | None:
    if not prices:
        return None
    s = sorted(prices)
    return s[len(s) // 2]


def _best_book(book_prices: dict[str, float]) -> tuple[float | None, str | None]:
    """Longest (best-for-the-bettor) price and the book offering it."""
    if not book_prices:
        return None, None
    book, price = max(book_prices.items(), key=lambda kv: kv[1])
    return price, book


def _extract_per_book(event: dict, swap_home_away: bool = False) -> dict[str, dict[str, dict]]:
    """Per-bookmaker prices keyed by our internal market names.

    Returns {market_key: {book: {"price", "point", "last_update"}}}. Any market whose key we
    don't recognise is skipped, so unsupported markets simply don't appear (render-if-present).
    """
    home_name = event.get("home_team", "")
    away_name = event.get("away_team", "")
    out: dict[str, dict[str, dict]] = {}

    for bm in event.get("bookmakers", []):
        book = bm.get("key", "?")
        bm_update = bm.get("last_update")
        for market in bm.get("markets", []):
            mkey = market.get("key")
            for outcome in market.get("outcomes", []):
                name = outcome.get("name", "")
                try:
                    price = float(outcome["price"])
                except (KeyError, TypeError, ValueError):
                    continue
                point = outcome.get("point")

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
                    if point is None or abs(float(point) - 2.5) > 0.01:
                        continue
                    key = "over_2_5" if name.lower() == "over" else "under_2_5"
                elif mkey == "btts":
                    key = "btts" if name.lower() in ("yes", "both teams to score") else "btts_no"
                else:
                    continue

                out.setdefault(key, {})[book] = {
                    "price": price, "point": point, "last_update": bm_update,
                }
    return out


async def refresh_odds_cache() -> None:
    global _odds_by_match, _book_odds, _cached_at

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
                global _quota_remaining
                remaining = resp.headers.get("x-requests-remaining", "?")
                try:
                    _quota_remaining = int(float(remaining))
                except (TypeError, ValueError):
                    _quota_remaining = None
                if _quota_remaining is not None and _quota_remaining <= _QUOTA_FLOOR:
                    logger.warning(
                        "Odds API quota low: %s requests left (floor %s) — value board/CLV will stale when exhausted",
                        _quota_remaining, _QUOTA_FLOOR,
                    )
                else:
                    logger.info("Odds API quota remaining: %s", remaining)
                if resp.status_code == 429:
                    logger.warning("Odds API rate-limited (429) — backing off until cache TTL")
                    _cached_at = now
                    return

                if resp.status_code == 404:
                    logger.info("WC 2026 not yet listed in The Odds API")
                    _cached_at = now
                    return
                if resp.status_code != 200:
                    logger.warning("Odds API %s: %s", resp.status_code, resp.text[:200])
                    _cached_at = now
                    return

                events = resp.json()
        except Exception as exc:
            logger.warning("Odds fetch failed: %s", exc)
            _cached_at = now
            return

        new_cache: dict[str, dict[str, float]] = {}
        new_books: dict[str, dict[str, dict[str, dict]]] = {}
        used_match_ids: set[str] = set()

        for event in events:
            commence_str = event.get("commence_time", "")
            try:
                commence_dt = datetime.fromisoformat(commence_str.replace("Z", "+00:00"))
            except Exception:
                continue

            event_home = event.get("home_team", "")
            event_away = event.get("away_team", "")

            candidates = [
                (kt, mid, hname, aname)
                for kt, mid, hname, aname in kickoff_index
                if abs((kt - commence_dt).total_seconds()) <= KICKOFF_WINDOW_SECS
                and mid not in used_match_ids
            ]
            if not candidates:
                continue

            best_mid: str | None = None
            best_score = 0.0
            best_swapped = False
            for _, mid, hname, aname in candidates:
                score_normal = (_name_score(event_home, hname) + _name_score(event_away, aname)) / 2.0
                score_swapped = (_name_score(event_home, aname) + _name_score(event_away, hname)) / 2.0
                if score_normal >= score_swapped and score_normal > best_score:
                    best_score, best_mid, best_swapped = score_normal, mid, False
                elif score_swapped > score_normal and score_swapped > best_score:
                    best_score, best_mid, best_swapped = score_swapped, mid, True

            if best_mid is None or best_score < 0.4:
                continue

            per_book = _extract_per_book(event, swap_home_away=best_swapped)
            if not per_book:
                continue
            new_books[best_mid] = per_book
            new_cache[best_mid] = {
                mkt: _median([d["price"] for d in books.values()])
                for mkt, books in per_book.items()
                if books
            }
            used_match_ids.add(best_mid)

        _odds_by_match = new_cache
        _book_odds = new_books
        _cached_at = now
        logger.info("Odds cache updated: %d matches with live odds", len(new_cache))

        cutoff = now - timedelta(hours=24)
        _STEAM_SNAPSHOTS[:] = [s for s in _STEAM_SNAPSHOTS if s[0] >= cutoff]
        if new_cache:
            import copy
            _STEAM_SNAPSHOTS.append((now, copy.deepcopy(new_cache)))
            if len(_STEAM_SNAPSHOTS) > _MAX_SNAPSHOTS:
                _STEAM_SNAPSHOTS.pop(0)


async def get_odds_for_match(match_id: str) -> dict[str, float]:
    """Median bookmaker price per market. The model/EV path reads this."""
    if not _odds_by_match and ODDS_API_KEY:
        await refresh_odds_cache()
    return _odds_by_match.get(match_id, {})


def get_book_odds_for_match(match_id: str) -> dict[str, dict]:
    """Best price + offering book per market for line-shopping.

    {market: {"books": {book: price}, "best_price": float, "best_book": str}}.
    """
    raw = _book_odds.get(match_id, {})
    out: dict[str, dict] = {}
    for market, books in raw.items():
        prices = {b: d["price"] for b, d in books.items() if d.get("price")}
        best_price, best_book = _best_book(prices)
        if best_price is None:
            continue
        out[market] = {"books": prices, "best_price": best_price, "best_book": best_book}
    return out


def match_arbitrage(book_odds: dict[str, dict], outcome_keys: tuple[str, ...]) -> dict | None:
    """Sure-bet check across the best price of each outcome of one market.

    Sum the implied probabilities at the best available price for each outcome; if it is
    below 1 the market is arbitrageable. With only three correlated books this is rare, so
    treat a flag as 'a genuinely good combined price', not an income engine.
    """
    legs = []
    s = 0.0
    for k in outcome_keys:
        entry = book_odds.get(k)
        if not entry or not entry.get("best_price"):
            return None
        price = entry["best_price"]
        s += 1.0 / price
        legs.append({"market": k, "best_price": price, "best_book": entry.get("best_book")})
    if s >= 1.0:
        return None
    return {"sum_implied": round(s, 4), "margin": round(1.0 - s, 4), "legs": legs}


def get_steam_signal(match_id: str, market: str, our_prob: float) -> dict | None:
    """Compare oldest vs newest snapshot to detect sharp money line movement."""
    if len(_STEAM_SNAPSHOTS) < 2:
        return None

    oldest_ts, oldest_cache = _STEAM_SNAPSHOTS[0]
    newest_ts, newest_cache = _STEAM_SNAPSHOTS[-1]

    old_odds = oldest_cache.get(match_id, {}).get(market)
    new_odds = newest_cache.get(match_id, {}).get(market)

    if not old_odds or not new_odds or old_odds <= 1.0 or new_odds <= 1.0:
        return None

    old_impl = 1.0 / old_odds
    new_impl = 1.0 / new_odds
    move = new_impl - old_impl

    if abs(move) < _STEAM_THRESHOLD:
        return None

    model_edge = our_prob - old_impl
    if (move > 0 and model_edge > 0) or (move < 0 and model_edge < 0):
        direction = "confirming"
    else:
        direction = "fading"

    age_hours = round((newest_ts - oldest_ts).total_seconds() / 3600, 1)
    return {
        "direction": direction,
        "move_pct": round(abs(move) * 100, 1),
        "age_hours": age_hours,
    }
