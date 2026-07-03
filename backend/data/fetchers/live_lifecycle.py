"""Match-lifecycle helpers for the live poller.

Extracted from live.py 2026-06-23 to keep the polling loop focused on
"fetch + persist + simulate" while the lifecycle decisions (when to mark
complete, how to handle SUSP/INT/PST/ABD/AWD, when to age out a long
delay) live here. Both this module and live.py share the status-taxonomy
constants, which live here as the single source of truth.

Behaviour invariants pinned by tests in:
  - backend/tests/test_match_interruption.py (lifecycle)
  - backend/tests/test_knockout_ft_trap.py (knockout FT gate)
  - backend/tests/test_concurrent_live_matches.py (concurrency)
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta
from typing import Optional

import httpx

from backend.db.models import LiveMatchState, Match

logger = logging.getLogger(__name__)

_API_KEY = os.getenv("API_FOOTBALL_KEY", "")
_BASE = "https://v3.football.api-sports.io"
_HEADERS = {"x-apisports-key": _API_KEY}

# --- Status taxonomy (single source of truth) ----------------------------------
# ET (extra-time playing), BT (break between ET halves) and P (penalty shootout
# in progress) are LIVE — the poller MUST keep ticking through them or we'd
# lose shootout events and the final score. _FT_STATUSES are the "match is
# decided" transitions; api-football drops the fixture from /fixtures?live=all
# once it hits one of these.
LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
FT_STATUSES = {"FT", "AET", "PEN"}

# Statuses that DECISIVELY end a match. Critically different from FT_STATUSES:
# FT is NOT decisive for a knockout match — api-football shows FT for ~30s when
# regulation ends before flipping to BT/ET. Treating FT as decisive would lock
# in the 90' score and render a stale "FT" for the entire 15-30min ET window.
# Only AET / PEN truly decide a knockout fixture.
KNOCKOUT_DECISIVE = {"AET", "PEN"}
# First WC2026 knockout matchday — group stage is 1-3, R32 is 4, R16 is 5,
# QF is 6, SF is 7, 3rd-place + Final is 8.
KNOCKOUT_MATCHDAY_FLOOR = 4

# Interruption taxonomy — see docs/plans/2026-06-23_match-interruption-handling.md.
# Pre-2026-06-23 these fell through the live-loop gate and the match silently
# became "complete" with whatever partial score was stored. FRA-IRQ (weather,
# suspended at HT) was the case that surfaced the bug.
DELAYED_STATUSES = {"SUSP", "INT"}          # paused, may resume same day
POSTPONED_STATUSES = {"PST", "TBD"}         # kickoff abandoned / not yet defined
ABANDONED_STATUSES = {"ABD", "CANC"}        # started, will not finish
AWARDED_STATUSES = {"AWD", "WO"}            # decided off-pitch

INTERRUPTION_MAP: dict[str, str] = {}
for _s in DELAYED_STATUSES:
    INTERRUPTION_MAP[_s] = "delayed"
for _s in POSTPONED_STATUSES:
    INTERRUPTION_MAP[_s] = "postponed"
for _s in ABANDONED_STATUSES:
    INTERRUPTION_MAP[_s] = "abandoned"
for _s in AWARDED_STATUSES:
    INTERRUPTION_MAP[_s] = "awarded"

# A delayed match flips to abandoned after this many hours so picks resolve
# via the void rule instead of dangling. FIFA's posture is "resume same or
# next day"; 24h is generous.
DELAYED_TO_ABANDONED_HOURS = 24


# --- Helpers -------------------------------------------------------------------

def is_knockout(match: Match) -> bool:
    """A match is a knockout fixture if it's matchday 4+. Belt-and-braces:
    matchday could be None for an admin-inserted bracket row — we err toward
    treating ambiguous as group-stage so we don't accidentally suppress an
    FT-complete for a normal match."""
    return (match.matchday or 0) >= KNOCKOUT_MATCHDAY_FLOOR


def is_decisive(status: str, match: Match) -> bool:
    """Should this status flip Match.status -> 'complete'?

    - Group stage (matchday 1-3): yes on FT / AET / PEN (only FT realistic).
    - Knockout (matchday >= 4): only on AET / PEN. FT is the brief
      regulation-end flag and could be heading to extra time.

    See docs/research/LIVE_KNOCKOUTS_AND_SHOOTOUTS.md for the trap analysis.
    """
    if status not in FT_STATUSES:
        return False
    if is_knockout(match):
        return status in KNOCKOUT_DECISIVE
    return True


def shootout_score(fx: dict) -> tuple[Optional[int], Optional[int]]:
    """Extract penalty-shootout score from a /fixtures response entry.

    api-football's score block has separate breakdowns:
        score.halftime, score.fulltime, score.extratime, score.penalty
    `goals.{home,away}` is the aggregate of regulation + ET (NOT shootout).
    The shootout tiebreaker lives ONLY in `score.penalty.{home,away}`,
    which is null/missing until shootout begins. Returns (home, away) where
    either can be None if the match never went to pens.
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


def _record_quota(r) -> None:
    """Mirror live.py — feed api-football headers to the quota counter."""
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


async def resolve_fixture_status(client: httpx.AsyncClient, fixture_id: int) -> Optional[dict]:
    """Hit /fixtures?id=X for one fixture. Returns {status, home_score,
    away_score, elapsed, extra, shootout_home, shootout_away} or None on any
    failure.

    Costs one api-football call. Used by the sweep to disambiguate "row
    is stale because match ended" from "row is stale because match was
    suspended and api-football dropped it from /fixtures?live=all" —
    impossible to tell from the LiveMatchState row alone.

    shootout_home/shootout_away come from score.penalty.{home,away}. Critical
    on knockout matches: when the fixture leaves /fixtures?live=all between
    status='P' (shootout in-play) and status='PEN' (decided), the live tick
    never sees the final PEN status; the stale sweep is what flips Match
    to complete, and without these fields the shootout score would be lost.
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
        so_home, so_away = shootout_score(fx)
        ft_home, ft_away = fulltime_score(fx)
        return {
            "status": st.get("short", ""),
            "home_score": goals.get("home"),
            "away_score": goals.get("away"),
            "elapsed": st.get("elapsed"),
            "extra": st.get("extra"),
            "shootout_home": so_home,
            "shootout_away": so_away,
            "ft_home": ft_home,
            "ft_away": ft_away,
        }
    except Exception as exc:
        logger.warning("resolve_fixture_status(%s) failed: %s", fixture_id, exc)
        return None


def fulltime_score(fx: dict) -> tuple[Optional[int], Optional[int]]:
    """Extract the 90-minute score from a /fixtures response entry.

    `score.fulltime.{home,away}` is the score at the END OF REGULATION —
    the horizon bookmaker 1X2/totals markets settle on. For matches that
    went to ET, `goals.{home,away}` diverges from this (reg+ET aggregate);
    settlement and calibration must use fulltime, display uses goals.
    """
    score = fx.get("score") or {}
    ft = score.get("fulltime") or {}
    return ft.get("home"), ft.get("away")


def _persist_shootout_on_finalize(match: Match, lms: Optional[LiveMatchState], truth: dict) -> None:
    """Copy a captured shootout score onto the Match row when finalizing.

    Belt-and-braces: takes the value from the API truth first (the freshest
    read), then falls back to whatever the live-tick path already wrote to
    LiveMatchState. The fallback matters for the GER-PAR class of bug where
    the fixture drops out of /fixtures?live=all between status='P' (shootout
    in-play, lms updated) and status='PEN' (decided) — the API truth on the
    PEN snapshot still has score.penalty populated, but if for any reason the
    API call returned partial data, the lms value preserves what the live
    ticks captured.
    """
    so_home = truth.get("shootout_home")
    so_away = truth.get("shootout_away")
    if so_home is None and lms is not None and lms.shootout_home_score is not None:
        so_home = lms.shootout_home_score
    if so_away is None and lms is not None and lms.shootout_away_score is not None:
        so_away = lms.shootout_away_score
    if so_home is not None:
        match.shootout_home_score = int(so_home)
        if lms is not None and lms.shootout_home_score != int(so_home):
            lms.shootout_home_score = int(so_home)
    if so_away is not None:
        match.shootout_away_score = int(so_away)
        if lms is not None and lms.shootout_away_score != int(so_away):
            lms.shootout_away_score = int(so_away)


def apply_interruption(
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
    interruption = INTERRUPTION_MAP.get(status_short)
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
        match.status = "abandoned"
    elif interruption == "postponed":
        match.status = "postponed"
    elif interruption == "awarded":
        # Awarded matches DO count for standings (3-0 walkover updates the
        # group table) but picks remain void per docs/plans/2026-06-23 §7b —
        # the void check is implemented in the settlement helpers, not here.
        match.status = "complete"
        if partial_home is not None:
            match.home_score = int(partial_home)
        if partial_away is not None:
            match.away_score = int(partial_away)
    # 'delayed' leaves Match.status untouched.


async def sweep_stale_live_rows(db, client: httpx.AsyncClient) -> None:
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
    cutoff = datetime.utcnow() - timedelta(minutes=5)
    stale = (
        db.query(LiveMatchState)
        .filter(LiveMatchState.status.in_(list(LIVE_STATUSES)))
        .filter(LiveMatchState.updated_at < cutoff)
        .all()
    )
    for lms in stale:
        m = db.query(Match).filter(Match.id == lms.match_id).first()
        if not m:
            continue
        truth = await resolve_fixture_status(client, lms.fixture_id_external) if lms.fixture_id_external else None
        if truth is None:
            # API didn't respond. Don't change anything — leaving the row in
            # its last live state is safer than guessing. Next pass tries again.
            logger.info("stale row %s: API verify failed, leaving as-is", lms.match_id)
            continue

        api_status = truth["status"]
        if api_status in FT_STATUSES:
            # Real FT (or AET/PEN). Use the API's authoritative score, not
            # the stale lms one.
            lms.status = api_status
            lms.home_score = truth["home_score"] if truth["home_score"] is not None else lms.home_score
            lms.away_score = truth["away_score"] if truth["away_score"] is not None else lms.away_score
            lms.updated_at = datetime.utcnow()
            # Knockout FT trap: stale sweep that sees status="FT" on a knockout
            # could be catching the 30-second gap before ET. Don't promote.
            if is_decisive(api_status, m) and m.status != "complete":
                m.status = "complete"
                if truth["home_score"] is not None:
                    m.home_score = int(truth["home_score"])
                if truth["away_score"] is not None:
                    m.away_score = int(truth["away_score"])
                if truth.get("ft_home") is not None:
                    m.ft_home_score = int(truth["ft_home"])
                if truth.get("ft_away") is not None:
                    m.ft_away_score = int(truth["ft_away"])
                _persist_shootout_on_finalize(m, lms, truth)
                m.interruption_status = None
                m.interruption_reason = None
                logger.info("stale row swept to %s: %s (verified, decisive)", api_status, lms.match_id)
            else:
                logger.info("stale row at %s but knockout still in play: %s", api_status, lms.match_id)
        elif api_status in LIVE_STATUSES:
            # Still live, our row just lost a few polls.
            lms.status = api_status
            lms.updated_at = datetime.utcnow()
            logger.info("stale row still live (%s): %s", api_status, lms.match_id)
        elif api_status in INTERRUPTION_MAP:
            apply_interruption(
                db, m, lms, api_status,
                truth.get("home_score"), truth.get("away_score"),
                reason=f"api-football status={api_status}",
            )
        else:
            logger.warning("stale row %s: unrecognised api status %r", lms.match_id, api_status)


async def watchdog_long_delayed(db, client: httpx.AsyncClient) -> None:
    """Sweep matches stuck in interruption_status='delayed' for too long.

    Two jobs:
      1. Re-verify with the API so a delayed match that ALREADY resumed
         and finished (without /fixtures?live=all ever showing it again,
         which happens sometimes) gets correctly marked complete.
      2. If the match has been delayed past DELAYED_TO_ABANDONED_HOURS
         and the API still shows it interrupted, flip to 'abandoned' so
         pick settlement can void cleanly instead of dangling forever.
    """
    delayed = (
        db.query(Match)
        .filter(Match.interruption_status == "delayed")
        .all()
    )
    if not delayed:
        return
    cutoff = datetime.utcnow() - timedelta(hours=DELAYED_TO_ABANDONED_HOURS)
    for m in delayed:
        lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == m.id).first()
        fixture_id = lms.fixture_id_external if lms else None
        if not fixture_id:
            continue
        truth = await resolve_fixture_status(client, fixture_id)
        if truth is None:
            continue
        api_status = truth["status"]
        if api_status in FT_STATUSES:
            if lms is not None:
                lms.status = api_status
                lms.home_score = truth["home_score"] if truth["home_score"] is not None else lms.home_score
                lms.away_score = truth["away_score"] if truth["away_score"] is not None else lms.away_score
                lms.updated_at = datetime.utcnow()
            # Same knockout-FT guard.
            if is_decisive(api_status, m):
                m.status = "complete"
                if truth["home_score"] is not None:
                    m.home_score = int(truth["home_score"])
                if truth["away_score"] is not None:
                    m.away_score = int(truth["away_score"])
                _persist_shootout_on_finalize(m, lms, truth)
                m.interruption_status = None
                m.interruption_reason = None
                logger.info("delayed match %s resolved to %s via watchdog (decisive)", m.id, api_status)
            else:
                logger.info("delayed match %s now at %s but knockout still in play", m.id, api_status)
            continue
        if api_status in LIVE_STATUSES:
            if lms is not None:
                lms.status = api_status
                lms.updated_at = datetime.utcnow()
            m.interruption_status = None
            m.interruption_reason = None
            logger.info("delayed match %s resumed live (%s)", m.id, api_status)
            continue
        if api_status in ABANDONED_STATUSES or api_status in AWARDED_STATUSES or api_status in POSTPONED_STATUSES:
            apply_interruption(
                db, m, lms, api_status,
                truth.get("home_score"), truth.get("away_score"),
                reason=f"api-football status={api_status}",
            )
            continue
        # Still SUSP/INT — age-out check.
        started = m.interruption_started_at or m.kickoff
        if started and started < cutoff:
            apply_interruption(
                db, m, lms, "ABD",
                truth.get("home_score") or m.partial_home_score,
                truth.get("away_score") or m.partial_away_score,
                reason=f"watchdog: delayed >{DELAYED_TO_ABANDONED_HOURS}h, api status still {api_status}",
            )
            logger.warning("delayed match %s aged out -> abandoned", m.id)
