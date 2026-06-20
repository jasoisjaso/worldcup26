"""Live in-play fixture poller.

Polls api-football's `/fixtures?live=all` for every WC2026 fixture currently in play,
ingests the score + elapsed minute + red cards + possession/shots/xG into
`LiveMatchState`, recomputes the in-play win probability via the Dixon-Coles restart
simulator, appends a tick to `LiveWpHistory`, and detects "big-moment" transitions
that trigger a push notification.

Request budget (api-football pro = 7,500/day, 300/min):
  * `/fixtures?live=all`        every 30s  → 2/min/match (~180/match for 90 min)
  * `/fixtures/events?fixture=` every 30s  → only when a match is live (~180/match)
  * `/fixtures/statistics?fix=` every 60s  → ~90/match (possession + xG)
  Per match peak: ~450/match (2 simultaneous = 900) — comfortable.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import httpx

from backend.data.fetchers.injuries import TEAM_IDS  # reuse the team-id map
from backend.db.session import SessionLocal
from backend.db.models import LiveMatchState, LiveWpHistory, Match, Team
from backend.models.live_wp import LiveState, simulate_live_wp

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# Map status from api-football to elapsed-minute semantics
_LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
_FT_STATUSES = {"FT", "AET", "PEN"}

# fixture_id ↔ match_id memo (api-football fixture id → our match.id)
_FIXTURE_MEMO: dict[int, str] = {}


def _resolve_match(db, fixture_id: int, home_id: int, away_id: int) -> Optional[Match]:
    """Resolve an api-football fixture to one of our WC matches. Cached after first hit.

    We match on (kickoff within 24h, home team api id, away team api id) using the
    existing TEAM_IDS reverse map.
    """
    if fixture_id in _FIXTURE_MEMO:
        return db.query(Match).filter(Match.id == _FIXTURE_MEMO[fixture_id]).first()

    # Reverse-lookup our team codes for the api-football team ids
    code_by_api = {v: k for k, v in TEAM_IDS.items()}
    home_code = code_by_api.get(home_id)
    away_code = code_by_api.get(away_id)
    if not home_code or not away_code:
        return None

    match = (
        db.query(Match)
        .filter(Match.home_code == home_code)
        .filter(Match.away_code == away_code)
        .order_by(Match.kickoff.desc())
        .first()
    )
    if match:
        _FIXTURE_MEMO[fixture_id] = match.id
    return match


def _parse_elapsed(api_elapsed: int | None, extra: int | None, status: str) -> int:
    """api-football's elapsed is minute (0-90+ext). Cap to our 95-minute model bound."""
    base = api_elapsed or 0
    e = extra or 0
    if status == "HT":
        return 45
    if status in ("FT", "AET", "PEN"):
        return 95
    return min(base + e, 95)


async def _fetch_events(client: httpx.AsyncClient, fixture_id: int) -> list[dict]:
    """Return event list for one fixture, or empty on any failure."""
    try:
        r = await client.get(f"{_BASE}/fixtures/events", params={"fixture": fixture_id}, headers=_HEADERS)
        if r.status_code != 200:
            return []
        return r.json().get("response", []) or []
    except Exception:
        return []


async def _fetch_stats_raw(client: httpx.AsyncClient, fixture_id: int) -> list[dict]:
    """Return the raw /fixtures/statistics response list (one entry per team)."""
    try:
        r = await client.get(f"{_BASE}/fixtures/statistics", params={"fixture": fixture_id}, headers=_HEADERS)
        if r.status_code != 200:
            return []
        return r.json().get("response", []) or []
    except Exception:
        return []


def _stats_raw_to_home_away(raw: list[dict]) -> dict:
    """Convert /fixtures/statistics raw response (team-keyed) into {home: {...}, away: {...}}.
    Caller must pass the home team's api id to disambiguate; for now we just trust order
    (api-football returns home first)."""
    if len(raw) < 2:
        return {}
    out: dict[str, dict] = {}
    for i, side in enumerate(("home", "away")):
        stats = {s.get("type"): s.get("value") for s in raw[i].get("statistics", [])}
        out[side] = stats
    return out


def _count_red_cards(events: list[dict], home_team_id: int) -> tuple[int, int]:
    """Count red cards per side from the event log."""
    home_red = away_red = 0
    for e in events:
        if e.get("type") == "Card" and e.get("detail") in ("Red Card", "Second Yellow card"):
            tid = (e.get("team") or {}).get("id")
            if tid == home_team_id:
                home_red += 1
            else:
                away_red += 1
    return home_red, away_red


def _stat_to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except Exception:
        return None


def _stat_to_pct(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str) and v.endswith("%"):
            return float(v.rstrip("%"))
        return float(v)
    except Exception:
        return None


def _stat_to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


# Per-fixture throttle state for the stats sub-fetch. Stats are cheap to cache
# in-process (just a list of dicts) and don't meaningfully shift faster than
# once a minute, so we fetch them every other 30s tick — halving the cost of
# live polling per match without visibly reducing freshness.
_STATS_TICK_COUNTER: dict[int, int] = {}
_LAST_STATS_RAW: dict[int, list] = {}


async def refresh_live_fixtures() -> None:
    """One full pass: fetch all WC live fixtures, update state + WP history.

    Designed to be called by the scheduler every 30 seconds. To keep us inside
    the api-football daily quota (7,500/day on Pro), this pass SKIPS the API
    entirely when no match is plausibly live — i.e. no kickoff within ±180min
    AND no LiveMatchState row currently in an in-play status. Saves ~95% of
    requests on no-match days (was 2,880/day baseline, now ~50-100/day).
    """
    if not _API_KEY:
        return

    # Cheap local check before any network call — avoids burning quota when
    # no World Cup match could possibly be live.
    db = SessionLocal()
    try:
        from datetime import timedelta as _td
        now = datetime.utcnow()
        live_window_lo = now - _td(minutes=180)
        live_window_hi = now + _td(minutes=180)

        any_in_play = (
            db.query(LiveMatchState)
            .filter(LiveMatchState.status.in_(list(_LIVE_STATUSES)))
            .first()
            is not None
        )
        any_kickoff_close = (
            db.query(Match)
            .filter(Match.kickoff >= live_window_lo)
            .filter(Match.kickoff <= live_window_hi)
            .first()
            is not None
        )

        if not any_in_play and not any_kickoff_close:
            # Still need to sweep stale rows even on the skip path (e.g. a match
            # ended 9min ago and went stale just after the last in-play tick).
            _sweep_stale_live_rows(db)
            db.commit()
            return
    finally:
        db.close()

    async with httpx.AsyncClient(timeout=20.0) as client:
        try:
            r = await client.get(f"{_BASE}/fixtures", params={"live": "all"}, headers=_HEADERS)
        except Exception as exc:
            logger.warning("live fixtures fetch failed: %s", exc)
            return
        if r.status_code != 200:
            logger.warning("live fixtures: HTTP %d %s", r.status_code, r.text[:120])
            return
        live_list = r.json().get("response", []) or []

        # Even when nothing is live we still need to sweep stale rows — a match
        # that ended 9 minutes ago is no longer in the live_list, but its row
        # is still in our DB stuck at 2H/95.
        if not live_list:
            db = SessionLocal()
            try:
                _sweep_stale_live_rows(db)
                db.commit()
            finally:
                db.close()
            return

        db = SessionLocal()
        try:
            for fx in live_list:
                fixture = fx.get("fixture") or {}
                teams = fx.get("teams") or {}
                goals = fx.get("goals") or {}
                status = (fixture.get("status") or {}).get("short", "")
                if status not in _LIVE_STATUSES and status not in _FT_STATUSES:
                    continue

                fixture_id = fixture.get("id")
                home_api = (teams.get("home") or {}).get("id")
                away_api = (teams.get("away") or {}).get("id")
                if not fixture_id or not home_api or not away_api:
                    continue

                match = _resolve_match(db, fixture_id, home_api, away_api)
                if not match:
                    continue  # not a WC fixture we track

                # Parse current state
                home_score = goals.get("home") or 0
                away_score = goals.get("away") or 0
                elapsed = _parse_elapsed(
                    (fixture.get("status") or {}).get("elapsed"),
                    (fixture.get("status") or {}).get("extra"),
                    status,
                )

                # Events fetched every tick (30s) — goals + cards need to be fresh
                # for the live ticker. Stats are heavier and only meaningfully change
                # every minute or so, so we throttle them to every other tick (60s
                # cadence). Saves ~180 calls/hr per live match without hurting UX.
                events = await _fetch_events(client, fixture_id)
                _STATS_TICK_COUNTER[fixture_id] = _STATS_TICK_COUNTER.get(fixture_id, 0) + 1
                if _STATS_TICK_COUNTER[fixture_id] % 2 == 1:
                    stats_raw = await _fetch_stats_raw(client, fixture_id)
                    _LAST_STATS_RAW[fixture_id] = stats_raw
                else:
                    stats_raw = _LAST_STATS_RAW.get(fixture_id, [])  # reuse cached
                stats = _stats_raw_to_home_away(stats_raw)

                # Persist everything we just pulled — this is the long-term archive.
                # Idempotent: events deduped on natural key, stats locked once is_final.
                try:
                    from backend.data.persistence import persist_events, persist_statistics
                    persist_events(db, match.id, fixture_id, events)
                    persist_statistics(
                        db, match.id, fixture_id, stats_raw,
                        is_final=status in _FT_STATUSES,
                    )
                except Exception as exc:
                    logger.warning("persistence failed for %s: %s", match.id, exc)

                h_red, a_red = _count_red_cards(events, home_api)

                # Statistics are best-effort — fail gracefully
                h_poss = _stat_to_pct((stats.get("home") or {}).get("Ball Possession"))
                a_poss = _stat_to_pct((stats.get("away") or {}).get("Ball Possession"))
                h_shots = _stat_to_int((stats.get("home") or {}).get("Total Shots"))
                a_shots = _stat_to_int((stats.get("away") or {}).get("Total Shots"))
                h_sot = _stat_to_int((stats.get("home") or {}).get("Shots on Goal"))
                a_sot = _stat_to_int((stats.get("away") or {}).get("Shots on Goal"))
                h_xg = _stat_to_float((stats.get("home") or {}).get("expected_goals"))
                a_xg = _stat_to_float((stats.get("away") or {}).get("expected_goals"))

                # Look up pre-match lambdas from the latest snapshot.
                # Without them we can't run the simulator — skip the tick.
                from backend.db.models import PredictionSnapshot
                snap = db.query(PredictionSnapshot).filter(PredictionSnapshot.match_id == match.id).first()
                if not snap or snap.lambda_home is None or snap.lambda_away is None:
                    continue

                # Simulate live WP
                wp = simulate_live_wp(
                    lambda_home=snap.lambda_home,
                    lambda_away=snap.lambda_away,
                    state=LiveState(
                        elapsed_min=elapsed,
                        home_score=home_score,
                        away_score=away_score,
                        home_red_cards=h_red,
                        away_red_cards=a_red,
                    ),
                )

                # Upsert LiveMatchState
                lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match.id).first()
                if lms is None:
                    lms = LiveMatchState(match_id=match.id, fixture_id_external=fixture_id)
                    db.add(lms)
                lms.status = status
                lms.elapsed_min = elapsed
                lms.home_score = home_score
                lms.away_score = away_score
                lms.home_red_cards = h_red
                lms.away_red_cards = a_red
                lms.home_possession = h_poss
                lms.away_possession = a_poss
                lms.home_shots = h_shots
                lms.away_shots = a_shots
                lms.home_shots_on_target = h_sot
                lms.away_shots_on_target = a_sot
                lms.home_xg = h_xg
                lms.away_xg = a_xg
                lms.updated_at = datetime.utcnow()

                # Dedup: only append a history tick if (elapsed, scores) changed
                last = (
                    db.query(LiveWpHistory)
                    .filter(LiveWpHistory.match_id == match.id)
                    .order_by(LiveWpHistory.id.desc())
                    .first()
                )
                changed = (
                    last is None
                    or last.elapsed_min != elapsed
                    or last.home_score != home_score
                    or last.away_score != away_score
                )

                # Big-moment push trigger: WP swung >= 15pts since last tick.
                # Pushes a notification with team names + new score. Dedup is per
                # (match, event_minute) so we never fire twice for the same goal.
                if last is not None and changed:
                    home = db.query(Team).filter(Team.code == match.home_code).first()
                    away = db.query(Team).filter(Team.code == match.away_code).first()
                    swing = max(
                        abs(wp.p_home - last.p_home),
                        abs(wp.p_away - last.p_away),
                    )
                    if swing >= 0.15 and home and away:
                        # Identify direction of swing
                        if wp.p_home > last.p_home:
                            mover, dir_label = home.name, "up"
                            new_pct = round(wp.p_home * 100)
                        else:
                            mover, dir_label = away.name, "up"
                            new_pct = round(wp.p_away * 100)
                        score = f"{home_score}–{away_score}"
                        title = f"{home.name} {score} {away.name}"
                        body = f"{mover} {dir_label} to {new_pct}% live — {elapsed}'"
                        try:
                            from backend.api.routes.push import send_push
                            send_push(
                                db,
                                title=title,
                                body=body,
                                url=f"/match/{match.id}",
                                dedup_key=f"swing:{match.id}:{elapsed}:{home_score}-{away_score}",
                            )
                        except Exception as exc:
                            logger.warning("push send for swing failed: %s", exc)

                if changed:
                    # Tag the tick with the most recent event label so the chart annotates it
                    label = None
                    for e in events[-1:]:
                        kind = e.get("type")
                        detail = e.get("detail")
                        player = (e.get("player") or {}).get("name") or ""
                        if kind == "Goal":
                            label = f"GOAL — {player}".strip(" —")
                        elif kind == "Card" and detail == "Red Card":
                            label = f"RED — {player}".strip(" —")
                    db.add(LiveWpHistory(
                        match_id=match.id,
                        elapsed_min=elapsed,
                        p_home=wp.p_home,
                        p_draw=wp.p_draw,
                        p_away=wp.p_away,
                        home_score=home_score,
                        away_score=away_score,
                        event_label=label,
                    ))

                # If the match has just ended, mark it complete in the main table.
                if status in _FT_STATUSES and match.status != "complete":
                    match.status = "complete"
                    match.home_score = home_score
                    match.away_score = away_score

                    # FT-finalize hook: lineups aren't in the per-tick path —
                    # if prematch_prefetch missed this match (e.g. lineups
                    # weren't published in time), grab them once now so the
                    # archive is complete. Events + statistics are already
                    # captured on the same tick a few lines above.
                    try:
                        from backend.data.persistence import persist_lineups as _persist_lineups
                        from backend.db.models import MatchLineup as _MatchLineup
                        already = (
                            db.query(_MatchLineup)
                            .filter(_MatchLineup.match_id == match.id)
                            .first()
                        )
                        if not already:
                            lr = await client.get(
                                f"{_BASE}/fixtures/lineups",
                                params={"fixture": fixture_id},
                                headers=_HEADERS,
                                timeout=15.0,
                            )
                            if lr.status_code == 200:
                                raw_lineups = lr.json().get("response", []) or []
                                if raw_lineups:
                                    n = _persist_lineups(db, match.id, fixture_id, raw_lineups)
                                    logger.info("FT-finalize: persisted %d lineup players for %s", n, match.id)
                    except Exception as exc:
                        logger.warning("FT-finalize lineup fetch failed for %s: %s", match.id, exc)

            # Stale-row sweep: api-football drops finished matches from
            # /fixtures?live=all, so a row stuck in 1H/HT/2H without a recent
            # update means the match ended. Flip those rows to FT and mark the
            # main Match complete using the last known LiveMatchState score.
            _sweep_stale_live_rows(db)

            db.commit()
        finally:
            db.close()


def _sweep_stale_live_rows(db: SessionLocal) -> None:
    """Find LiveMatchState rows in an in-play status that haven't been touched
    in 5+ minutes. The live poller runs every 30s, so a 5-minute gap (10
    missed polls) is conclusive proof api-football dropped the fixture from
    /fixtures?live=all — i.e. it ended. Tightened from 8min after a Turkey-
    Paraguay match left a ghost row on the live page for too long after FT.
    """
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    stale = (
        db.query(LiveMatchState)
        .filter(LiveMatchState.status.in_(list(_LIVE_STATUSES)))
        .filter(LiveMatchState.updated_at < cutoff)
        .all()
    )
    for lms in stale:
        lms.status = "FT"
        m = db.query(Match).filter(Match.id == lms.match_id).first()
        if m and m.status != "complete":
            m.status = "complete"
            if lms.home_score is not None:
                m.home_score = lms.home_score
            if lms.away_score is not None:
                m.away_score = lms.away_score
        logger.info("stale live row swept to FT: %s (last update %s)", lms.match_id, lms.updated_at)
