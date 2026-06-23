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

# Map status from api-football to elapsed-minute semantics.
# IMPORTANT: ET (extra-time playing), BT (break between ET halves) and P
# (penalty shootout in progress) are ALL live statuses — the poller MUST
# keep ticking through them or we'd lose the spot-kick events and the
# final score (knockout games can swing twice in extra time + go to pens
# and we want the full event log captured). _FT_STATUSES is for the
# "match is now decided" transitions where we mark the row complete and
# stop polling on the NEXT pass (api-football drops the fixture from
# /fixtures?live=all once it hits FT/AET/PEN).
_LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
_FT_STATUSES = {"FT", "AET", "PEN"}

# Statuses that DECISIVELY end a match. Critically different from _FT_STATUSES:
# FT is NOT decisive for a knockout match — api-football shows FT for a few
# seconds at the end of regulation before flipping to BT/ET when the match is
# going to extra time (confirmed in api-football + Sportmonks docs). Treating
# FT as final on a knockout would lock in the 90' draw and show a stale score
# for the entire ET period. Only AET / PEN truly decide a knockout fixture.
_KNOCKOUT_DECISIVE = {"AET", "PEN"}
# First WC2026 knockout matchday — group stage is 1-3, R32 is 4, R16 is 5,
# QF is 6, SF is 7, 3rd-place is 8, Final is 8. matchday >= 4 == knockout.
_KNOCKOUT_MATCHDAY_FLOOR = 4


def _is_knockout(match: Match) -> bool:
    """A match is a knockout fixture if it's matchday 4+. Belt-and-braces:
    matchday could be None for an admin-inserted bracket row, in which case
    fall back to a None `group` (group-stage matches always have a group
    code). We err toward treating ambiguous as group-stage so we don't
    accidentally suppress an FT-complete for a normal match."""
    md = match.matchday or 0
    return md >= _KNOCKOUT_MATCHDAY_FLOOR


def _is_decisive(status: str, match: Match) -> bool:
    """Should this status flip Match.status -> 'complete'?

    - Group stage (matchday 1-3): yes on FT / AET / PEN (only FT realistic).
    - Knockout (matchday >= 4): only on AET / PEN. FT is the brief
      regulation-end flag and could be heading to extra time.

    See docs/research/LIVE_KNOCKOUTS_AND_SHOOTOUTS.md for the trap analysis.
    """
    if status not in _FT_STATUSES:
        return False
    if _is_knockout(match):
        return status in _KNOCKOUT_DECISIVE
    return True


def _shootout_score(fx: dict) -> tuple[Optional[int], Optional[int]]:
    """Extract penalty-shootout score from a /fixtures response entry.

    api-football's score block has separate breakdowns:
        score.halftime, score.fulltime, score.extratime, score.penalty
    `goals.{home,away}` is the aggregate of regulation + ET (NOT shootout).
    The shootout tiebreaker lives ONLY in `score.penalty.{home,away}`,
    which is null/missing until shootout begins. We surface it as
    (home, away) where either can be None if the match never went to pens.
    """
    score = fx.get("score") or {}
    pen = score.get("penalty") or {}
    h = pen.get("home")
    a = pen.get("away")
    if h is None and a is None:
        return None, None
    try:
        return (int(h) if h is not None else None, int(a) if a is not None else None)
    except (ValueError, TypeError):
        return None, None

# Interruption taxonomy — see docs/plans/2026-06-23_match-interruption-handling.md.
# Pre-2026-06-23 these all fell through the gate at the bottom of the live
# loop and the match silently became "complete" with whatever partial score
# was stored. FRA-IRQ (weather, suspended at HT) is the case that surfaced
# the bug. _DELAYED keep getting polled (cheap single-fixture endpoint via
# the watchdog) so the row flips back to live the moment play resumes; the
# others are terminal-ish and stop polling.
_DELAYED_STATUSES = {"SUSP", "INT"}          # paused, may resume same day
_POSTPONED_STATUSES = {"PST", "TBD"}         # kickoff abandoned / not yet defined
_ABANDONED_STATUSES = {"ABD", "CANC"}        # started, will not finish
_AWARDED_STATUSES = {"AWD", "WO"}            # decided off-pitch

# Status short → interruption_status the Match row should carry.
_INTERRUPTION_MAP: dict[str, str] = {}
for _s in _DELAYED_STATUSES:
    _INTERRUPTION_MAP[_s] = "delayed"
for _s in _POSTPONED_STATUSES:
    _INTERRUPTION_MAP[_s] = "postponed"
for _s in _ABANDONED_STATUSES:
    _INTERRUPTION_MAP[_s] = "abandoned"
for _s in _AWARDED_STATUSES:
    _INTERRUPTION_MAP[_s] = "awarded"

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


# Number of hours a match can stay in interruption_status='delayed' before
# the watchdog flips it to 'abandoned'. 24h is generous: FIFA's own posture
# is to resume within the same or next day. Pick void / standings update
# triggers once we flip — see docs/plans/2026-06-23 §7b.
_DELAYED_TO_ABANDONED_HOURS = 24


async def _resolve_fixture_status(client: httpx.AsyncClient, fixture_id: int) -> Optional[dict]:
    """Hit /fixtures?id=X for one fixture. Returns {status, home_score,
    away_score, elapsed} or None on any failure.

    Costs one api-football call. Used by the sweep to disambiguate "row
    is stale because match ended" from "row is stale because match was
    suspended and api-football dropped it from /fixtures?live=all" —
    impossible to tell from the LiveMatchState row alone.
    """
    try:
        r = await client.get(f"{_BASE}/fixtures", params={"id": fixture_id}, headers=_HEADERS)
        _record_quota(r)
        if r.status_code != 200:
            return None
        resp = r.json().get("response", []) or []
        if not resp:
            return None
        fx = resp[0]
        st = (fx.get("fixture") or {}).get("status") or {}
        goals = fx.get("goals") or {}
        return {
            "status": st.get("short", ""),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "elapsed": st.get("elapsed"),
            "extra": st.get("extra"),
        }
    except Exception as exc:
        logger.warning("resolve_fixture_status(%s) failed: %s", fixture_id, exc)
        return None


def _apply_interruption(
    db,
    match: Match,
    lms: Optional[LiveMatchState],
    status_short: str,
    partial_home: Optional[int],
    partial_away: Optional[int],
    reason: str,
) -> None:
    """Mark a Match as interrupted (delayed / postponed / abandoned / awarded).

    Critical invariant: never copy a partial score into Match.home_score /
    Match.away_score, because those drive calibration, standings, group
    tables, and the bracket projection. The partial sits in the
    partial_* columns until either the match resumes-and-finishes (the
    live loop will then write the real FT) or the watchdog declares it
    permanently abandoned (picks void, partial stays for the recap card).
    """
    interruption = _INTERRUPTION_MAP.get(status_short)
    if interruption is None:
        return  # unknown status — leave the row alone

    # First-time entry into a non-NULL interruption: stamp the timestamp
    # so the watchdog can age it later. Don't overwrite on repeated polls.
    if match.interruption_status != interruption:
        match.interruption_started_at = datetime.utcnow()
        logger.info(
            "match %s -> interruption=%s (api status %s, reason=%s)",
            match.id, interruption, status_short, reason,
        )
    match.interruption_status = interruption
    match.interruption_reason = reason
    if partial_home is not None:
        match.partial_home_score = int(partial_home)
    if partial_away is not None:
        match.partial_away_score = int(partial_away)

    # Reflect the real status in LiveMatchState so the operator/admin view
    # shows "INT" or "SUSP" instead of a frozen 1H/HT.
    if lms is not None:
        lms.status = status_short
        lms.updated_at = datetime.utcnow()

    if interruption == "abandoned":
        # Picks gate on Match.status != 'complete'; standings + group table
        # consumers already filter on `status='complete'`, so an abandoned
        # match correctly disappears from both.
        match.status = "abandoned"
    elif interruption == "postponed":
        match.status = "postponed"
    elif interruption == "awarded":
        # Awarded matches DO count for standings (3-0 walkover updates the
        # group table) but picks remain void per §7b — the void check is
        # implemented in the settlement helpers, not here.
        match.status = "complete"
        if partial_home is not None:
            match.home_score = int(partial_home)
        if partial_away is not None:
            match.away_score = int(partial_away)
    # 'delayed' leaves Match.status untouched (was 'upcoming' or whatever
    # it became when the match kicked off — usually still 'upcoming' since
    # we only flip to 'complete' on FT). Resumption picks back up normally.


async def _sweep_stale_live_rows(db, client: httpx.AsyncClient) -> None:
    """Verify-then-mark sweep for live rows that haven't been touched in 5+ min.

    Pre-2026-06-23 this function assumed "stale = FT" and blindly marked
    the Match complete with the last known score. That's wrong whenever
    api-football drops the fixture for a non-FT reason (SUSP, INT, PST,
    ABD, AWD) — most catastrophically on the FRA-IRQ weather suspension,
    where a 1-0 at HT was promoted to "FT 1-0" in our DB.

    Now: for each stale row, one cheap /fixtures?id=X call resolves the
    actual current status, and we route to either FT-completion or the
    interruption-handling path. Worst case one API call per stale row
    per pass — bounded by the number of in-play matches (typically 0-2).
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
        m = db.query(Match).filter(Match.id == lms.match_id).first()
        if not m:
            continue
        truth = await _resolve_fixture_status(client, lms.fixture_id_external) if lms.fixture_id_external else None
        if truth is None:
            # API didn't respond. Don't change anything — leaving the row in
            # its last live state is safer than guessing. Next pass tries again.
            logger.info("stale row %s: API verify failed, leaving as-is", lms.match_id)
            continue

        api_status = truth["status"]
        if api_status in _FT_STATUSES:
            # Real FT (or AET/PEN). Use the API's authoritative score, not
            # the stale lms one.
            lms.status = api_status
            lms.home_score = truth["home_score"] if truth["home_score"] is not None else lms.home_score
            lms.away_score = truth["away_score"] if truth["away_score"] is not None else lms.away_score
            lms.updated_at = datetime.utcnow()
            # KNOCKOUT TRAP again: a sweep that sees status="FT" on a knockout
            # could be catching the 30-second gap before ET. Don't promote to
            # complete — leave it live and let the next sweep pick up AET/PEN.
            # The live row still gets refreshed; only the Match.status lock is
            # held back. Same fix as the main loop above.
            if _is_decisive(api_status, m) and m.status != "complete":
                m.status = "complete"
                if truth["home_score"] is not None:
                    m.home_score = int(truth["home_score"])
                if truth["away_score"] is not None:
                    m.away_score = int(truth["away_score"])
                # Clear any prior interruption — match really did finish.
                m.interruption_status = None
                m.interruption_reason = None
                logger.info("stale row swept to %s: %s (verified, decisive)", api_status, lms.match_id)
            else:
                logger.info("stale row at %s but knockout still in play: %s", api_status, lms.match_id)
        elif api_status in _LIVE_STATUSES:
            # Still live, our row just lost a few polls. Refresh status +
            # let the next normal pass pick it up via /fixtures?live=all.
            lms.status = api_status
            lms.updated_at = datetime.utcnow()
            logger.info("stale row still live (%s): %s", api_status, lms.match_id)
        elif api_status in _INTERRUPTION_MAP:
            # The reason the row went stale — match is interrupted.
            _apply_interruption(
                db, m, lms, api_status,
                truth.get("home_score"), truth.get("away_score"),
                reason=f"api-football status={api_status}",
            )
        else:
            # Unknown status (NS, TBD, etc.) — leave alone, log so we notice.
            logger.warning("stale row %s: unrecognised api status %r", lms.match_id, api_status)


async def _watchdog_long_delayed(db, client: httpx.AsyncClient) -> None:
    """Sweep matches stuck in interruption_status='delayed' for too long.

    Two jobs:
      1. Re-verify with the API so a delayed match that ALREADY resumed
         and finished (without /fixtures?live=all ever showing it again,
         which happens sometimes) gets correctly marked complete with the
         right score.
      2. If the match has been delayed past _DELAYED_TO_ABANDONED_HOURS
         and the API still shows it interrupted, flip to 'abandoned' so
         pick settlement can void cleanly instead of dangling forever.
    """
    from datetime import datetime, timedelta
    delayed = (
        db.query(Match)
        .filter(Match.interruption_status == "delayed")
        .all()
    )
    if not delayed:
        return
    cutoff = datetime.utcnow() - timedelta(hours=_DELAYED_TO_ABANDONED_HOURS)
    for m in delayed:
        lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == m.id).first()
        fixture_id = lms.fixture_id_external if lms else None
        if not fixture_id:
            continue
        truth = await _resolve_fixture_status(client, fixture_id)
        if truth is None:
            continue
        api_status = truth["status"]
        if api_status in _FT_STATUSES:
            # Match resumed AND finished. Capture the real status / score.
            if lms is not None:
                lms.status = api_status
                lms.home_score = truth["home_score"] if truth["home_score"] is not None else lms.home_score
                lms.away_score = truth["away_score"] if truth["away_score"] is not None else lms.away_score
                lms.updated_at = datetime.utcnow()
            # Same knockout-FT guard as the main loop and the sweep — don't
            # mark a knockout complete just because regulation FT showed up.
            if _is_decisive(api_status, m):
                m.status = "complete"
                if truth["home_score"] is not None:
                    m.home_score = int(truth["home_score"])
                if truth["away_score"] is not None:
                    m.away_score = int(truth["away_score"])
                # Resumption cleared the interruption — match is honestly complete now.
                m.interruption_status = None
                m.interruption_reason = None
                logger.info("delayed match %s resolved to %s via watchdog (decisive)", m.id, api_status)
            else:
                logger.info("delayed match %s now at %s but knockout still in play", m.id, api_status)
            continue
        if api_status in _LIVE_STATUSES:
            # Resumed and currently playing. Next live pass will tick it.
            if lms is not None:
                lms.status = api_status
                lms.updated_at = datetime.utcnow()
            m.interruption_status = None
            m.interruption_reason = None
            logger.info("delayed match %s resumed live (%s)", m.id, api_status)
            continue
        if api_status in _ABANDONED_STATUSES or api_status in _AWARDED_STATUSES or api_status in _POSTPONED_STATUSES:
            _apply_interruption(
                db, m, lms, api_status,
                truth.get("home_score"), truth.get("away_score"),
                reason=f"api-football status={api_status}",
            )
            continue
        # Still SUSP/INT — age-out check.
        started = m.interruption_started_at or m.kickoff
        if started and started < cutoff:
            _apply_interruption(
                db, m, lms, "ABD",
                truth.get("home_score") or m.partial_home_score,
                truth.get("away_score") or m.partial_away_score,
                reason=f"watchdog: delayed >{_DELAYED_TO_ABANDONED_HOURS}h, api status still {api_status}",
            )
            logger.warning("delayed match %s aged out -> abandoned", m.id)
