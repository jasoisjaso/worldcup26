"""Golden Boot Watch — WC2026 top scorers leaderboard from api-football.

Refreshes hourly (top-scorer data only updates after matches complete). Cached in
memory; the API route reads from this cache so frontend never hits api-football
directly. Single endpoint, single request, no rate budget concern.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime

import httpx

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

_WC_LEAGUE_ID = 1
_WC_SEASON = 2026

# Module-level cache: {data: [...], fetched_at: datetime}
_cache: dict = {"data": [], "fetched_at": None}


async def refresh_topscorers() -> None:
    """Fetch the current Golden Boot leaderboard and cache it.

    Quota-gated: when remaining api-football credit dips below the live
    reserve floor we skip this entirely so the in-play poller keeps headroom.

    Skips gracefully when no goals have been scored yet (the endpoint returns an
    empty list). Designed to be called by the scheduler every hour.
    """
    if not _API_KEY:
        return

    # Quota guard — when below the live reserve floor, skip entirely.
    from backend.data import quota_budget as _qb
    if not _qb.small_job_allowed():
        return

    try:
        async with httpx.AsyncClient(timeout=15.0) as c:
            r = await c.get(
                f"{_BASE}/players/topscorers",
                params={"league": _WC_LEAGUE_ID, "season": _WC_SEASON},
                headers=_HEADERS,
            )
            # Feed quota counter
            try:
                rem = int(r.headers.get("x-ratelimit-requests-remaining", ""))
                _qb.update_quota(rem)
            except Exception:
                pass
            if r.status_code != 200:
                logger.warning("topscorers: HTTP %d %s", r.status_code, r.text[:120])
                return
            response = r.json().get("response", []) or []

        out = []
        for row in response:
            player = row.get("player") or {}
            stats = (row.get("statistics") or [{}])[0]
            team = stats.get("team") or {}
            goals = stats.get("goals") or {}
            games = stats.get("games") or {}
            cards = stats.get("cards") or {}

            n_goals = goals.get("total")
            if n_goals is None:
                continue
            out.append({
                "player_id": player.get("id"),
                "name": player.get("name"),
                "firstname": player.get("firstname"),
                "lastname": player.get("lastname"),
                "nationality": player.get("nationality"),
                "photo": player.get("photo"),
                "team_id": team.get("id"),
                "team_name": team.get("name"),
                "team_logo": team.get("logo"),
                "goals": n_goals,
                "assists": (goals.get("assists") or 0),
                "appearances": games.get("appearences") or 0,  # api spelling
                "minutes": games.get("minutes") or 0,
                "yellow_cards": (cards.get("yellow") or 0) + (cards.get("yellowred") or 0),
                "red_cards": cards.get("red") or 0,
            })
        # API returns sorted by goals desc already, but enforce it
        out.sort(key=lambda x: (x["goals"] or 0, x["assists"] or 0), reverse=True)
        _cache["data"] = out
        _cache["fetched_at"] = datetime.utcnow()
        logger.info("topscorers refreshed: %d players", len(out))
    except Exception as exc:
        logger.warning("topscorers refresh failed: %s", exc)


def get_topscorers() -> dict:
    """Returns the cached leaderboard with a fetched_at timestamp."""
    return {
        "fetched_at": _cache["fetched_at"].isoformat() if _cache["fetched_at"] else None,
        "leaderboard": _cache["data"],
    }
