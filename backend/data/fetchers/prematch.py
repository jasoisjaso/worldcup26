"""Pre-match data prefetcher.

Walks every WC2026 match in the kickoff window and persists api-football's signals
ONCE per match. After this job runs, the data is in the DB forever and we never call
api-football for it again (except H2H which we refresh after each new match between
the two teams).

Windows:
  * 24h pre-kickoff  → /predictions  → ApiFootballPrediction (one row per match)
  * 60min pre-kickoff → /fixtures/lineups → MatchLineup + MatchLineupPlayer
  * Any time both teams known → /fixtures/headtohead → MatchH2H (grows over time)

Scheduler interval: 15min. The job is cheap when nothing's pending and idempotent
when something already exists.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.data.fetchers.injuries import TEAM_IDS
from backend.data.persistence import (
    persist_api_prediction,
    persist_h2h,
    persist_lineups,
)
from backend.db.models import (
    ApiFootballPrediction,
    LiveMatchState,
    Match,
    MatchH2H,
    MatchLineup,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# How far ahead to look for matches to prefetch
_PREDICTION_WINDOW_HOURS = 24
_LINEUP_WINDOW_HOURS = 2  # api-football usually publishes lineups ~60 min before
_H2H_REFRESH_DAYS = 30   # only re-pull H2H if our cached set is older than this


async def _resolve_fixture_id(
    client: httpx.AsyncClient,
    home_code: str,
    away_code: str,
    kickoff: datetime,
) -> Optional[int]:
    """Find the api-football fixture id for a WC match by querying the day's fixtures."""
    hid = TEAM_IDS.get(home_code)
    aid = TEAM_IDS.get(away_code)
    if not hid or not aid:
        return None
    date_str = kickoff.strftime("%Y-%m-%d")
    try:
        r = await client.get(
            f"{_BASE}/fixtures",
            params={"league": 1, "season": 2026, "date": date_str},
            headers=_HEADERS,
        )
        if r.status_code != 200:
            return None
        for fx in (r.json().get("response", []) or []):
            t = fx.get("teams") or {}
            home = (t.get("home") or {}).get("id")
            away = (t.get("away") or {}).get("id")
            if home == hid and away == aid:
                return (fx.get("fixture") or {}).get("id")
    except Exception as exc:
        logger.warning("fixture-id resolve failed for %s vs %s: %s", home_code, away_code, exc)
    return None


async def _get_fixture_id(client: httpx.AsyncClient, db, match: Match) -> Optional[int]:
    """Return api-football fixture id for a Match, using LiveMatchState cache first."""
    lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match.id).first()
    if lms and lms.fixture_id_external:
        return lms.fixture_id_external
    fid = await _resolve_fixture_id(client, match.home_code, match.away_code, match.kickoff)
    if fid:
        # Store on a NEW LiveMatchState row so the live poller can use it too
        if not lms:
            lms = LiveMatchState(match_id=match.id, fixture_id_external=fid, status="NS")
            db.add(lms)
        else:
            lms.fixture_id_external = fid
    return fid


async def _fetch_prediction(client: httpx.AsyncClient, fixture_id: int) -> Optional[dict]:
    try:
        r = await client.get(
            f"{_BASE}/predictions",
            params={"fixture": fixture_id},
            headers=_HEADERS,
        )
        if r.status_code != 200:
            return None
        rows = r.json().get("response", []) or []
        return rows[0] if rows else None
    except Exception as exc:
        logger.warning("prediction fetch %s failed: %s", fixture_id, exc)
        return None


async def _fetch_lineups(client: httpx.AsyncClient, fixture_id: int) -> list[dict]:
    try:
        r = await client.get(
            f"{_BASE}/fixtures/lineups",
            params={"fixture": fixture_id},
            headers=_HEADERS,
        )
        if r.status_code != 200:
            return []
        return r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("lineup fetch %s failed: %s", fixture_id, exc)
        return []


async def _fetch_h2h(client: httpx.AsyncClient, hid: int, aid: int) -> list[dict]:
    try:
        r = await client.get(
            f"{_BASE}/fixtures/headtohead",
            params={"h2h": f"{hid}-{aid}", "last": 20},
            headers=_HEADERS,
        )
        if r.status_code != 200:
            return []
        return r.json().get("response", []) or []
    except Exception as exc:
        logger.warning("h2h fetch %s-%s failed: %s", hid, aid, exc)
        return []


async def prefetch_pending_matches() -> dict:
    """Walk every WC match in the next 24h. For each:
       * if no prediction stored → fetch + store ApiFootballPrediction
       * if within 2h of kickoff and no lineup stored → fetch + store MatchLineup
       * if no recent H2H → fetch + store MatchH2H

    Returns a summary dict of work done."""
    summary = {"predictions": 0, "lineups": 0, "h2h": 0, "skipped": 0, "errors": 0}
    if not _API_KEY:
        return summary

    now = datetime.utcnow()
    pred_window_end = now + timedelta(hours=_PREDICTION_WINDOW_HOURS)
    lineup_window_end = now + timedelta(hours=_LINEUP_WINDOW_HOURS)

    db = SessionLocal()
    try:
        pending = (
            db.query(Match)
            .filter(Match.kickoff != None)
            .filter(Match.kickoff > now - timedelta(minutes=30))
            .filter(Match.kickoff <= pred_window_end)
            .order_by(Match.kickoff.asc())
            .all()
        )
        if not pending:
            return summary

        async with httpx.AsyncClient(timeout=15.0) as client:
            for m in pending:
                # 1) Prediction — once per match
                has_pred = (
                    db.query(ApiFootballPrediction)
                    .filter(ApiFootballPrediction.match_id == m.id)
                    .first()
                )
                # 2) Lineup — once per match (when it's been published)
                has_lineup = (
                    db.query(MatchLineup)
                    .filter(MatchLineup.match_id == m.id)
                    .first()
                )

                # 3) H2H freshness — refresh if older than threshold
                hid = TEAM_IDS.get(m.home_code)
                aid = TEAM_IDS.get(m.away_code)
                t1, t2 = (hid, aid) if hid and aid and hid < aid else (aid, hid)
                latest_h2h = None
                if t1 and t2:
                    latest_h2h = (
                        db.query(MatchH2H)
                        .filter(MatchH2H.team1_id == t1, MatchH2H.team2_id == t2)
                        .order_by(MatchH2H.captured_at.desc())
                        .first()
                    )

                needs_pred = not has_pred
                needs_lineup = not has_lineup and m.kickoff <= lineup_window_end
                needs_h2h = (
                    not latest_h2h
                    or (now - latest_h2h.captured_at) > timedelta(days=_H2H_REFRESH_DAYS)
                )

                if not (needs_pred or needs_lineup or needs_h2h):
                    summary["skipped"] += 1
                    continue

                fid = await _get_fixture_id(client, db, m)
                if not fid:
                    summary["errors"] += 1
                    continue

                if needs_pred:
                    raw = await _fetch_prediction(client, fid)
                    if raw and persist_api_prediction(db, m.id, fid, raw):
                        summary["predictions"] += 1

                if needs_lineup:
                    raw = await _fetch_lineups(client, fid)
                    if raw:
                        n = persist_lineups(db, m.id, fid, raw)
                        if n:
                            summary["lineups"] += n

                if needs_h2h and hid and aid:
                    raw = await _fetch_h2h(client, hid, aid)
                    if raw:
                        n = persist_h2h(db, raw)
                        summary["h2h"] += n

                db.commit()

        return summary
    finally:
        db.close()
