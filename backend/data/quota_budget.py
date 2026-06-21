"""Unified quota budget — shared by harvester, auto_backfill, and injuries_persist.

One process-level counter tracks the last known api-football daily call count
seen in a response header (`x-ratelimit-requests-remaining`). Every consumer
updates it after a successful call, and reads it for gating.

Three phases within the 24h UTC day:
  Phase 1 (hour 0-1):   backfill fires, harvester stays quiet.
                         Budget: backfill gets up to 150 calls (enough for the
                         28-match archive gap), then stops.
  Phase 2 (hour 1-22):  harvester runs, paced to stay above the live reserve.
                         Budget: tiered pacing — fast above 3000, slow at 1000,
                         refuses at LIVE_RESERVE_FLOOR (1000).
  Phase 3 (hour 22-24): "use it up" — harvester burns the remaining quota down
                         to 0 so no calls are wasted. The live poller won't fire
                         near midnight UTC anyway (no kickoffs at that time).

The harvester writes `remaining` back to this module after every call so all
consumers share one number without redundant /status probes.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Disk persistence — survives container restart. Written to /app/data which is
# volume-mounted alongside the sqlite DB, so a deploy or crash mid-day does
# NOT wipe the in-memory quota counter on restart. Without this, the gates
# revert to defaults and the few jobs that fire while we're "unknown" burn
# API blind. File stores {date, quota_remaining, daily_calls_made}; restored
# at module import.
_QUOTA_STATE_FILE = os.path.join(
    os.environ.get("WC26_STATE_DIR", "/app/data"),
    ".wc26_quota_state.json",
)


# ---- Master kill switch ---------------------------------------------------
#
# Set WC26_HARVEST=0 in your environment to disable EVERY api-football consumer
# (harvester, auto_backfill, injuries_persist). Use this on a local/dev machine
# that shares the production API_FOOTBALL_KEY but should never burn quota.
#
# Default is enabled — production sets nothing, local .env sets WC26_HARVEST=0.
#
# This is the single switch the operator flips. It does NOT touch the live
# poller (scores, odds, events for live matches) because those are needed for
# the UI even in local dev. It only gates the slow background fillers.

def harvester_enabled() -> bool:
    # Runtime pause flipped from the admin UI wins over the env default — the
    # operator must be able to stop the burn from a phone without a redeploy.
    # The import is deferred to avoid a circular dependency at module load
    # (runtime_settings → models → session, which transitively pulls quota_budget
    # back in via the harvester package on cold start).
    try:
        from backend.data.runtime_settings import harvest_paused as _paused
        if _paused():
            return False
    except Exception:
        pass
    return os.getenv("WC26_HARVEST", "1") not in ("0", "false", "False", "no")

# ---- Budget tuning --------------------------------------------------------

# Daily quota for api-football Pro tier.
API_DAILY_QUOTA = 7500

# The floor the live poller needs. Harvester refuses to go below this except
# in Phase 3 (the final window before UTC midnight, when no matches are live).
# 2026-06-21: lifted to 1,250 (was 1,000) so even an all-day three-match
# slate of WC fixtures has ~5h of polling headroom inside the reserve.
LIVE_RESERVE_FLOOR = 1250

# Backfill budget: max calls allowed in a single UTC day. 28 matches × 5
# endpoints = 140. Pad to 200 for safety against partial runs.
BACKFILL_MAX_CALLS = 200

# Phase windows, in hours from UTC midnight.
PHASE1_HOURS = 1.0    # backfill window
# 50-min burn window (was 2h). Combined with the 5-sec burst job in
# refresh.py this drains 1,250 calls in ~10-15 min comfortably, then idles
# the rest of the window — no API blast, just guaranteed not-wasting.
PHASE3_HOURS = 50.0 / 60.0

# Small emergency floor for live polling inside the burn window. Calls below
# this stop firing the harvester even mid-burn so a match that overlaps the
# UTC-midnight handover (rare for WC, common-enough for European leagues we
# might add later) doesn't get starved. 100 calls ≈ 30 min of an active live
# match poll, so it absorbs the worst case.
PHASE3_BUFFER = 100

# Tiered pacing for Phase 2:
#   above FAST_ABOVE:  1 job per tick (every 5 min)
#   between SLOW_BELOW and FAST_ABOVE:  1 job every other tick
#   below SLOW_BELOW:  refuse (keep the live reserve)
FAST_ABOVE = 3000
SLOW_BELOW = 1500


# ---- In-process state -----------------------------------------------------

# Last api-football remaining count; None until first successful call.
_quota_remaining: int | None = None

# Last api-football PER-MINUTE remaining (X-RateLimit-Remaining header).
# Observational only — used by the admin dashboard's per-minute mini-gauge to
# spot when burst burn is approaching the 300/min hard cap. Not used to gate
# anything (the daily counter is the binding constraint for our load).
_per_minute_remaining: int | None = None

# Track how many calls we've made today (backfill + harvester + injuries).
_daily_calls_made: int = 0

# Backfill call counter for today.
_backfill_calls_today: int = 0

# Date of last observed quota reading.
_last_read_date: str | None = None

# Harvester ticks skipped in a row (for the "every other tick" pace).
_tick_counter: int = 0

# Date we observed a "request limit for the day" body. Resets when day rolls.
# Consumers set via mark_quota_exhausted() and read via quota_exhausted_today().
_QUOTA_EXHAUSTED_DATE: str | None = None


def mark_quota_exhausted() -> None:
    """Call when api-football body contains 'request limit for the day'."""
    global _QUOTA_EXHAUSTED_DATE
    _QUOTA_EXHAUSTED_DATE = _today_utc_iso()


def quota_exhausted_today() -> bool:
    return _QUOTA_EXHAUSTED_DATE == _today_utc_iso()


# ---- Public API -----------------------------------------------------------

def _today_utc_iso() -> str:
    return datetime.utcnow().date().isoformat()


def reset_if_new_day() -> bool:
    """Reset state when UTC date rolls over. Returns True if reset happened."""
    global _daily_calls_made, _backfill_calls_today, _last_read_date, _tick_counter
    today = _today_utc_iso()
    if _last_read_date != today:
        _daily_calls_made = 0
        _backfill_calls_today = 0
        _tick_counter = 0
        _last_read_date = today
        # Don't reset _quota_remaining — it was stale from yesterday. The
        # first real call after reset will populate it.
        return True
    return False


def _persist_state() -> None:
    """Write current quota state to disk so it survives container restart."""
    try:
        with open(_QUOTA_STATE_FILE, "w") as f:
            json.dump({
                "date": _today_utc_iso(),
                "quota_remaining": _quota_remaining,
                "daily_calls_made": _daily_calls_made,
                "backfill_calls_today": _backfill_calls_today,
                "exhausted_date": _QUOTA_EXHAUSTED_DATE,
            }, f)
    except Exception:
        pass


def _restore_state() -> None:
    """On module import, restore quota state from disk if same UTC day."""
    global _quota_remaining, _daily_calls_made, _backfill_calls_today
    global _last_read_date, _QUOTA_EXHAUSTED_DATE
    try:
        if not os.path.exists(_QUOTA_STATE_FILE):
            return
        with open(_QUOTA_STATE_FILE) as f:
            d = json.load(f)
        if d.get("date") == _today_utc_iso():
            _quota_remaining = d.get("quota_remaining")
            _daily_calls_made = d.get("daily_calls_made", 0)
            _backfill_calls_today = d.get("backfill_calls_today", 0)
            _last_read_date = _today_utc_iso()
            ex = d.get("exhausted_date")
            if ex == _today_utc_iso():
                _QUOTA_EXHAUSTED_DATE = ex
    except Exception:
        pass


def update_quota(remaining: int | None, per_minute_remaining: int | None = None) -> None:
    """Call after every api-football response to keep the counter fresh.

    `remaining` is the daily counter (X-RateLimit-Requests-Remaining).
    `per_minute_remaining` is the per-minute counter (X-RateLimit-Remaining)
    — observational only, surfaces in /harvester/overview for the admin UI.
    """
    global _quota_remaining, _daily_calls_made, _per_minute_remaining
    if remaining is not None:
        _quota_remaining = remaining
        _daily_calls_made += 1
    if per_minute_remaining is not None:
        _per_minute_remaining = per_minute_remaining
    reset_if_new_day()
    _persist_state()


def per_minute_remaining() -> int | None:
    """Last observed X-RateLimit-Remaining (per-minute). Resets each minute on
    the API side; we only learn its current value from response headers."""
    return _per_minute_remaining


def record_backfill_call() -> None:
    """Increment the backfill-specific call counter."""
    global _backfill_calls_today
    _backfill_calls_today += 1
    reset_if_new_day()


def quota_remaining() -> int | None:
    """Last known remaining from api-football headers. None if unknown."""
    reset_if_new_day()
    return _quota_remaining


# Call _restore_state() at module-import time so a container restart picks up
# the last persisted quota counter instead of starting from None.
_restore_state()


def daily_calls_made() -> int:
    reset_if_new_day()
    return _daily_calls_made


# ---- Phase detection ------------------------------------------------------

def _hours_since_midnight_utc() -> float:
    now = datetime.utcnow()
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return (now - midnight).total_seconds() / 3600.0


def _hours_until_midnight_utc() -> float:
    now = datetime.utcnow()
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    return (tomorrow - now).total_seconds() / 3600.0


def in_phase1() -> bool:
    """First hour after reset. Backfill should run; harvester should wait."""
    return _hours_since_midnight_utc() < PHASE1_HOURS


def in_phase3() -> bool:
    """Last two hours before reset. Burn remaining quota."""
    return _hours_until_midnight_utc() < PHASE3_HOURS


# ---- Consumer gating ------------------------------------------------------

def backfill_can_run() -> bool:
    """Backfill is allowed only in Phase 1 and only within its daily budget."""
    if not harvester_enabled():
        return False
    reset_if_new_day()
    if _backfill_calls_today >= BACKFILL_MAX_CALLS:
        return False
    # In phase 1 OR if quota is healthy (not exhausted yet). After phase 1 we
    # still let an incomplete backfill finish if it started, but no new start.
    if not in_phase1() and _backfill_calls_today == 0:
        return False
    if _quota_remaining is not None and _quota_remaining < 200:
        return False  # gobbling 140 calls when only 200 left is too aggressive
    return True


def harvester_can_run() -> bool:
    """Harvester can run, paced by remaining quota and time phase."""
    global _tick_counter
    if not harvester_enabled():
        return False
    reset_if_new_day()
    _tick_counter += 1

    # Phase 1: let the backfill go first.
    if in_phase1():
        return False

    if _quota_remaining is None:
        # SAFE-BY-DEFAULT: we don't know yet, BLOCK rather than probe-burn.
        # The live poller is unrestricted and will populate the counter on
        # its next cycle. Harvester wakes up once we have an observation.
        return False

    # Phase 3: burn everything down to PHASE3_BUFFER.
    if in_phase3():
        return _quota_remaining > PHASE3_BUFFER

    # Phase 2: paced.
    if _quota_remaining < LIVE_RESERVE_FLOOR:
        return False

    if _quota_remaining < SLOW_BELOW:
        # Below 1500: one call every 6 ticks (30 min).
        return _tick_counter % 6 == 0

    if _quota_remaining < FAST_ABOVE:
        # 1500-3000: every other tick (10 min).
        return _tick_counter % 2 == 0

    # Above 3000: every tick (5 min).
    return True


def burn_should_fire() -> bool:
    """Gate for the burn-mode tick (5-sec interval job in refresh.py).

    True only inside the Phase 3 burn window AND while quota is above
    PHASE3_BUFFER. Outside Phase 3 this is a no-op so the burst job costs
    nothing the rest of the day. Honours the harvester-paused toggle so the
    operator can still freeze everything from the admin UI.
    """
    if not harvester_enabled():
        return False
    reset_if_new_day()
    if not in_phase3():
        return False
    if _quota_remaining is None:
        return False  # SAFE-BY-DEFAULT — wait for live poller to probe
    return _quota_remaining > PHASE3_BUFFER


def small_job_allowed() -> bool:
    """Gate for the smaller-frequency jobs that hit api-football (prematch
    prefetch, topscorers, etc).

    SAFE-BY-DEFAULT: when we have no quota observation yet (fresh container
    start, before the live poller has touched the API), we BLOCK these jobs.
    The live poller is unrestricted and will populate the counter on its
    next 30s tick. Small jobs then wake up automatically. Worst-case
    delay is one polling cycle; benefit is we never blind-burn quota during
    the post-restart window — which is when we historically lost the most."""
    reset_if_new_day()
    if _quota_remaining is None:
        return False  # SAFE-BY-DEFAULT — wait for live poller to probe
    return _quota_remaining > LIVE_RESERVE_FLOOR


def injuries_can_run() -> bool:
    """Persistent injury layer (48 calls per cycle). Only run when quota is
    comfortable. Don't run in Phase 1 (let backfill go first)."""
    if not harvester_enabled():
        return False
    reset_if_new_day()
    if in_phase1():
        return False
    if _quota_remaining is None:
        # SAFE-BY-DEFAULT: don't probe-burn 96 calls when we don't know.
        return False
    return _quota_remaining > 2000  # comfortable buffer


def budget_summary() -> dict:
    """Human-readable snapshot for /health and admin endpoints.

    Adds a `burn_rate_per_hour` so we can spot quota runaway early — if the
    burn extrapolates to > daily quota with hours left, raise alarm.
    Adds a `projection` showing whether we'll blow the day at current rate.
    """
    h = _hours_since_midnight_utc()
    burn_per_hour = round((_daily_calls_made / h), 0) if h > 0.1 and _daily_calls_made > 0 else 0
    hours_left = _hours_until_midnight_utc()
    projected_total = _daily_calls_made + (burn_per_hour * hours_left) if burn_per_hour else 0
    alert = (
        "EXHAUST_RISK" if projected_total > API_DAILY_QUOTA
        else "TIGHT" if projected_total > API_DAILY_QUOTA * 0.85
        else "OK"
    )
    return {
        "hours_since_midnight_utc": round(h, 1),
        "hours_until_reset": round(hours_left, 1),
        "phase": 1 if in_phase1() else 3 if in_phase3() else 2,
        "phase_label": "backfill" if in_phase1() else "burn" if in_phase3() else "harvest",
        "quota_remaining": _quota_remaining,
        "per_minute_remaining": _per_minute_remaining,
        # Surface the floors so the admin UI can render reserve-line markers
        # and tooltips without hard-coding constants on the FE side.
        "live_reserve_floor": LIVE_RESERVE_FLOOR,
        "burn_buffer": PHASE3_BUFFER,
        "burn_window_minutes": round(PHASE3_HOURS * 60),
        "daily_calls_made": _daily_calls_made,
        "daily_quota": API_DAILY_QUOTA,
        "burn_rate_per_hour": burn_per_hour,
        "projected_daily_total": round(projected_total, 0),
        "projection_alert": alert,
        "backfill_calls_today": _backfill_calls_today,
        "harvester_tick": _tick_counter,
        "harvester_enabled": harvester_enabled(),
        "backfill_allowed": backfill_can_run(),
        "harvester_allowed": harvester_can_run(),
        "burn_should_fire": burn_should_fire(),
        "injuries_allowed": injuries_can_run(),
    }
