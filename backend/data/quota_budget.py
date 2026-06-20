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

import logging
import os
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


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
    return os.getenv("WC26_HARVEST", "1") not in ("0", "false", "False", "no")

# ---- Budget tuning --------------------------------------------------------

# Daily quota for api-football Pro tier.
API_DAILY_QUOTA = 7500

# The floor the live poller needs. Harvester refuses to go below this except
# in Phase 3 (the final hour before UTC midnight, when no matches are live).
LIVE_RESERVE_FLOOR = 1000

# Backfill budget: max calls allowed in a single UTC day. 28 matches × 5
# endpoints = 140. Pad to 200 for safety against partial runs.
BACKFILL_MAX_CALLS = 200

# Phase windows, in hours from UTC midnight.
PHASE1_HOURS = 1.0    # backfill window
PHASE3_HOURS = 2.0    # last N hours before reset: burn remaining quota

# Tiered pacing for Phase 2:
#   above FAST_ABOVE:  1 job per tick (every 5 min)
#   between SLOW_BELOW and FAST_ABOVE:  1 job every other tick
#   below SLOW_BELOW:  refuse (keep the live reserve)
FAST_ABOVE = 3000
SLOW_BELOW = 1500


# ---- In-process state -----------------------------------------------------

# Last api-football remaining count; None until first successful call.
_quota_remaining: int | None = None

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


def update_quota(remaining: int | None) -> None:
    """Call after every api-football response to keep the counter fresh."""
    global _quota_remaining, _daily_calls_made
    if remaining is not None:
        _quota_remaining = remaining
        _daily_calls_made += 1
    reset_if_new_day()


def record_backfill_call() -> None:
    """Increment the backfill-specific call counter."""
    global _backfill_calls_today
    _backfill_calls_today += 1
    reset_if_new_day()


def quota_remaining() -> int | None:
    """Last known remaining from api-football headers. None if unknown."""
    reset_if_new_day()
    return _quota_remaining


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
        return True  # we don't know yet; one probe call is fine

    # Phase 3: burn everything down to 0.
    if in_phase3():
        # Still leave a tiny buffer (50 calls) for the last breath of the
        # live poller in case a match somehow kicks off at 11:55pm UTC.
        return _quota_remaining > 50

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
        return True
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
        "daily_calls_made": _daily_calls_made,
        "burn_rate_per_hour": burn_per_hour,
        "projected_daily_total": round(projected_total, 0),
        "projection_alert": alert,
        "backfill_calls_today": _backfill_calls_today,
        "harvester_tick": _tick_counter,
        "harvester_enabled": harvester_enabled(),
        "backfill_allowed": backfill_can_run(),
        "harvester_allowed": harvester_can_run(),
        "injuries_allowed": injuries_can_run(),
    }
