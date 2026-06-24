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
from backend.data.fetchers.live_lifecycle import (
    apply_interruption as _apply_interruption,
    is_decisive as _is_decisive,
    resolve_fixture_status as _resolve_fixture_status,
    shootout_score as _shootout_score,
    sweep_stale_live_rows as _sweep_stale_live_rows,
    watchdog_long_delayed as _watchdog_long_delayed,
    FT_STATUSES as _FT_STATUSES,
    INTERRUPTION_MAP as _INTERRUPTION_MAP,
    LIVE_STATUSES as _LIVE_STATUSES,
    # Re-exported for backwards compat with test_match_interruption.py which
    # imports the underscored alias. New code should import from live_lifecycle.
    DELAYED_TO_ABANDONED_HOURS as _DELAYED_TO_ABANDONED_HOURS,
)
from backend.db.session import SessionLocal
from backend.db.models import LiveMatchState, LiveWpHistory, Match, Team
from backend.models.live_wp import LiveState, simulate_live_wp

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}


def _record_quota(r) -> None:
    """Feed api-football response headers back into the shared quota counter.

    The live poller used to be silent here, so quota_budget._quota_remaining
    stayed frozen at whatever the harvester last observed. That made the
    admin dashboard look stuck during Phase 1 (when only live polling fires)
    and worse, broke the chicken-and-egg seal on restart — the safe-by-default
    gates only unlocked once the harvester made a call, but the harvester
    refused until quota was observed. Cheap to call: just reads two headers
    that are already on the response.
    """
    try:
        from backend.data import quota_budget as _qb
        daily = r.headers.get("x-ratelimit-requests-remaining")
        per_min = r.headers.get("x-ratelimit-remaining")
        _qb.update_quota(
            int(daily) if daily and daily.isdigit() else None,
            int(per_min) if per_min and per_min.isdigit() else None,
        )
    except Exception:
        pass

# Status taxonomy + lifecycle helpers (interruption / sweep / watchdog / knockout-FT
# gate / shootout-score reader) live in backend.data.fetchers.live_lifecycle —
# imported at the top of this file. See that module for the full contract.

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
    """Map api-football's elapsed/extra/status to a display minute.

    Returns a wall-clock-ish minute up to ~130 so a knockout match that goes
    to ET or penalties has honest x-axis values on the WP chart. The PRE-2026-06-23
    version clamped at 95 and flattened all of ET into the same tick, which
    made the chart useless for "how did the swing look in extra time" — and
    on a shootout night (Argentina/Austria, Messi's miss) erased the timeline
    almost entirely.

    The 95-min cap that the in-play simulator needs is applied SEPARATELY at
    the simulate_live_wp() call site — this function reports reality, the
    simulator can clamp its own input.
    """
    base = api_elapsed or 0
    e = extra or 0
    if status == "HT":
        return 45
    if status == "BT":      # break between extra-time periods
        return 105
    if status == "P":       # penalty shootout in progress
        return 125
    if status == "FT":
        return 90
    if status == "AET":     # extra time finished, no shootout
        return 120
    if status == "PEN":     # shootout decided
        return 125
    # Live play: cap at 130 so a runaway elapsed value can't break the chart axis.
    return min(base + e, 130)


async def _fetch_events(client: httpx.AsyncClient, fixture_id: int) -> list[dict]:
    """Return event list for one fixture, or empty on any failure."""
    try:
        r = await client.get(f"{_BASE}/fixtures/events", params={"fixture": fixture_id}, headers=_HEADERS)
        _record_quota(r)
        if r.status_code != 200:
            return []
        return r.json().get("response", []) or []
    except Exception:
        return []


async def _fetch_stats_raw(client: httpx.AsyncClient, fixture_id: int) -> list[dict]:
    """Return the raw /fixtures/statistics response list (one entry per team)."""
    try:
        r = await client.get(f"{_BASE}/fixtures/statistics", params={"fixture": fixture_id}, headers=_HEADERS)
        _record_quota(r)
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


# Per-fixture throttle state. Stats are cheap to cache in-process and don't
# meaningfully shift faster than ~90s, so we fetch them every THIRD 30s tick
# (was every-other — tightened 2026-06-23 ahead of MD3 to extend per-match
# budget). For 12 simultaneous matches across MD3 that's 360 calls/day
# saved vs the old cadence with no visible UX cost.
_STATS_TICK_COUNTER: dict[int, int] = {}
_LAST_STATS_RAW: dict[int, list] = {}

# Smart events-skip. The /fixtures/events endpoint returns the cumulative
# event log; if nothing happened since our last fetch we'd burn an API call
# for an identical payload. We skip the fetch when:
#   * elapsed hasn't advanced by >= EVENTS_REFETCH_GAP_MIN minutes AND
#   * score hasn't changed AND
#   * red-card counts haven't changed (no new red since last tick)
# A goal or red ALWAYS forces a refetch on the next tick so the ticker
# stays sharp. Halftime/break ticks still fetch periodically for subs.
# Saves ~60-75% of events calls during quiet first halves.
_LAST_EVENTS_PAYLOAD: dict[int, list] = {}      # fixture_id -> last events
_LAST_EVENTS_TICK: dict[int, dict] = {}         # fixture_id -> {elapsed, h, a, hr, ar}
EVENTS_REFETCH_GAP_MIN = 2  # minutes — force refetch even if nothing else changed


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
            # Sweep now needs the API client to verify FT vs INT/SUSP, so we
            # open a short-lived one rather than re-using the main path's.
            async with httpx.AsyncClient(timeout=20.0) as _c:
                await _sweep_stale_live_rows(db, _c)
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
        _record_quota(r)
        if r.status_code != 200:
            logger.warning("live fixtures: HTTP %d %s", r.status_code, r.text[:120])
            return
        live_list = r.json().get("response", []) or []

        # Even when nothing is live we still need to sweep stale rows — a match
        # that ended 9 minutes ago is no longer in the live_list, but its row
        # is still in our DB stuck at 2H/95. The sweep now verifies the real
        # current status per fixture (FT vs INT/SUSP/PST/ABD) so a weather
        # suspension doesn't get silently upgraded to FT (the FRA-IRQ bug).
        if not live_list:
            db = SessionLocal()
            try:
                await _sweep_stale_live_rows(db, client)
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

                fixture_id = fixture.get("id")
                home_api = (teams.get("home") or {}).get("id")
                away_api = (teams.get("away") or {}).get("id")
                if not fixture_id or not home_api or not away_api:
                    continue

                # api-football occasionally lists SUSP/INT fixtures in
                # /fixtures?live=all briefly before dropping them. Route
                # them through the interruption handler instead of the
                # silent skip that used to live here (which is what let
                # the FRA-IRQ row get marked FT via the stale-sweep path).
                if status in _INTERRUPTION_MAP:
                    match = _resolve_match(db, fixture_id, home_api, away_api)
                    if match:
                        lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match.id).first()
                        _apply_interruption(
                            db, match, lms, status,
                            goals.get("home"), goals.get("away"),
                            reason=f"api-football status={status}",
                        )
                    continue

                if status not in _LIVE_STATUSES and status not in _FT_STATUSES:
                    continue

                match = _resolve_match(db, fixture_id, home_api, away_api)
                if not match:
                    continue  # not a WC fixture we track

                # Resumption: a previously delayed match is back in /fixtures?
                # live=all in a live status — clear the interruption marker so
                # the UI stops showing the "paused" badge and calibration
                # treats the FT (when it comes) as a normal completion.
                if match.interruption_status == "delayed" and status in _LIVE_STATUSES:
                    logger.info("match %s resumed (status %s), clearing interruption", match.id, status)
                    match.interruption_status = None
                    match.interruption_reason = None

                # Parse current state
                home_score = goals.get("home") or 0
                away_score = goals.get("away") or 0
                # Shootout score lives in score.penalty.* — separate from
                # goals.* (which is regulation + ET). Both may be None until
                # the shootout begins; both are populated for the duration
                # of status="P" and frozen at status="PEN".
                so_home, so_away = _shootout_score(fx)
                elapsed = _parse_elapsed(
                    (fixture.get("status") or {}).get("elapsed"),
                    (fixture.get("status") or {}).get("extra"),
                    status,
                )

                # Smart events-skip — see _LAST_EVENTS_TICK comment block.
                # Re-fetch events only when the state has actually moved or
                # we've been stale for >= EVENTS_REFETCH_GAP_MIN minutes.
                # The /fixtures?live=all response we're already inside this
                # loop on gives us elapsed + scores cheaply — that's what we
                # compare against. Red cards aren't on the parent response
                # so we can only detect them via a periodic refresh, hence
                # the time-based fallback.
                last_evt = _LAST_EVENTS_TICK.get(fixture_id)
                api_elapsed = (fixture.get("status") or {}).get("elapsed") or 0
                api_h_score = goals.get("home") or 0
                api_a_score = goals.get("away") or 0
                should_refetch_events = (
                    last_evt is None
                    or api_h_score != last_evt["h"]
                    or api_a_score != last_evt["a"]
                    or (api_elapsed - (last_evt.get("e") or 0)) >= EVENTS_REFETCH_GAP_MIN
                )
                if should_refetch_events:
                    events = await _fetch_events(client, fixture_id)
                    _LAST_EVENTS_PAYLOAD[fixture_id] = events
                    _LAST_EVENTS_TICK[fixture_id] = {
                        "e": api_elapsed, "h": api_h_score, "a": api_a_score,
                    }
                else:
                    # Reuse the cached payload — persist_events is idempotent
                    # so re-passing it is a cheap no-op (no DB writes either).
                    events = _LAST_EVENTS_PAYLOAD.get(fixture_id, [])

                # Stats — every third tick (90s cadence). Tightened from
                # every-other (60s) ahead of MD3 simultaneous fixtures.
                _STATS_TICK_COUNTER[fixture_id] = _STATS_TICK_COUNTER.get(fixture_id, 0) + 1
                if _STATS_TICK_COUNTER[fixture_id] % 3 == 1:
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

                # Simulate live WP. Pass the live xG totals so the simulator can
                # weight the remaining minutes toward who's actually creating
                # chances — not just the scoreline (no-op until xG is available
                # and enough minutes have elapsed; see live_wp._adjust_for_live_xg).
                # WP simulator only models regulation (95-min cap). Clamp here
                # so ET / shootout minutes don't push the remaining-minutes
                # term negative — display `elapsed` itself can still be 120+
                # for the chart axis.
                wp = simulate_live_wp(
                    lambda_home=snap.lambda_home,
                    lambda_away=snap.lambda_away,
                    state=LiveState(
                        elapsed_min=min(elapsed, 95),
                        home_score=home_score,
                        away_score=away_score,
                        home_red_cards=h_red,
                        away_red_cards=a_red,
                        home_xg=h_xg,
                        away_xg=a_xg,
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
                # Shootout score — only write when present so a regulation tick
                # never overwrites a previously-captured shootout score.
                if so_home is not None:
                    lms.shootout_home_score = so_home
                if so_away is not None:
                    lms.shootout_away_score = so_away
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
                # KNOCKOUT TRAP: api-football shows status="FT" for ~30s when a
                # knockout match reaches the end of regulation before flipping
                # to BT/ET — locking in the 90' score here would render a stale
                # "final" for the entire ET period. _is_decisive() gates that
                # off and waits for AET/PEN on knockouts. Group-stage FT is
                # decisive as before.
                if _is_decisive(status, match) and match.status != "complete":
                    match.status = "complete"
                    match.home_score = home_score
                    match.away_score = away_score
                    # Persist shootout score onto the Match row too, so the
                    # bracket / standings / report-card readers don't have to
                    # join LiveMatchState. None-safe: regulation-decided matches
                    # leave these NULL.
                    if so_home is not None:
                        match.shootout_home_score = so_home
                    if so_away is not None:
                        match.shootout_away_score = so_away

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
                            _record_quota(lr)
                            if lr.status_code == 200:
                                raw_lineups = lr.json().get("response", []) or []
                                if raw_lineups:
                                    n = _persist_lineups(db, match.id, fixture_id, raw_lineups)
                                    logger.info("FT-finalize: persisted %d lineup players for %s", n, match.id)
                    except Exception as exc:
                        logger.warning("FT-finalize lineup fetch failed for %s: %s", match.id, exc)

            # Stale-row sweep: api-football drops fixtures from
            # /fixtures?live=all not only when they hit FT/AET/PEN but also
            # when they go SUSP/INT/PST/ABD. Verifying the actual current
            # status per fixture (one cheap call per stale row) is the only
            # way to tell weather-suspended from real-FT — the FRA-IRQ bug
            # was the blind "stale = FT" assumption that used to live here.
            await _sweep_stale_live_rows(db, client)

            # Also catch matches that have been delayed for hours but never
            # rejoined /fixtures?live=all (api-football sometimes leaves them
            # in INT for days before flipping to ABD). The watchdog flips
            # them to abandoned once they've been delayed past the per-comp
            # cutoff so picks resolve via the void rule instead of dangling.
            await _watchdog_long_delayed(db, client)

            db.commit()
        finally:
            db.close()
