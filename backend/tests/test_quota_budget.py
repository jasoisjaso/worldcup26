"""Verify the quota-budget gates do what the admin claims they do.

These tests exercise the pure decision functions (harvester_can_run,
burn_should_fire, budget_summary). No HTTP, no DB — we manipulate the
module-level globals directly because that's exactly how update_quota +
the phase clock would set them in production.
"""
from __future__ import annotations

import os

os.environ.setdefault("WC26_STATE_DIR", "/tmp/wc26_test_state")
os.makedirs(os.environ["WC26_STATE_DIR"], exist_ok=True)

import pytest  # noqa: E402

from backend.data import quota_budget as qb  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(monkeypatch):
    """Reset module state between tests so order doesn't matter.

    We also force the harvester-enabled gate to True (env default) so a stale
    SettingsKV row from another test can't mask the assertions here.
    """
    monkeypatch.delenv("WC26_HARVEST", raising=False)
    qb._quota_remaining = None
    qb._per_minute_remaining = None
    qb._daily_calls_made = 0
    qb._backfill_calls_today = 0
    qb._tick_counter = 0
    qb._last_read_date = qb._today_utc_iso()
    qb._QUOTA_EXHAUSTED_DATE = None
    # Belt-and-braces: clear any persisted SettingsKV row for the harvest pause
    try:
        from backend.data.runtime_settings import set_harvest_paused
        set_harvest_paused(False)
    except Exception:
        pass
    yield


def _force_phase2(monkeypatch):
    """Pretend we're in the middle of the day so phase 2 gates apply."""
    monkeypatch.setattr(qb, "in_phase1", lambda: False)
    monkeypatch.setattr(qb, "in_phase3", lambda: False)


def _force_phase3(monkeypatch):
    monkeypatch.setattr(qb, "in_phase1", lambda: False)
    monkeypatch.setattr(qb, "in_phase3", lambda: True)


def test_live_reserve_floor_is_2500():
    """Single-point contract test for the user-set floor (Ultra plan, 2026-06-21)."""
    assert qb.LIVE_RESERVE_FLOOR == 2500


def test_daily_quota_is_75000():
    """Ultra plan ceiling — drives projection alerts in budget_summary."""
    assert qb.API_DAILY_QUOTA == 75000


def test_burn_window_is_120_minutes():
    """2h burn window (lifted from 50min on the Ultra plan, 2026-06-21)."""
    assert round(qb.PHASE3_HOURS * 60) == 120


def test_burn_buffer_is_100():
    assert qb.PHASE3_BUFFER == 100


def test_harvester_blocked_below_reserve_in_phase2(monkeypatch):
    _force_phase2(monkeypatch)
    qb._quota_remaining = qb.LIVE_RESERVE_FLOOR - 1   # 2499
    qb._tick_counter = 0
    assert qb.harvester_can_run() is False


def test_harvester_runs_above_reserve_in_phase2(monkeypatch):
    _force_phase2(monkeypatch)
    qb._quota_remaining = 5000   # fast tier
    qb._tick_counter = 0
    assert qb.harvester_can_run() is True


def test_burn_should_fire_only_in_phase3(monkeypatch):
    qb._quota_remaining = 500
    _force_phase2(monkeypatch)
    assert qb.burn_should_fire() is False, "must not burn outside the window"

    _force_phase3(monkeypatch)
    assert qb.burn_should_fire() is True


def test_burn_should_fire_respects_buffer(monkeypatch):
    _force_phase3(monkeypatch)

    qb._quota_remaining = qb.PHASE3_BUFFER + 1  # 101
    assert qb.burn_should_fire() is True

    qb._quota_remaining = qb.PHASE3_BUFFER       # 100 — exactly at floor
    assert qb.burn_should_fire() is False, "must stop at the buffer to protect live polling"

    qb._quota_remaining = 50  # below buffer
    assert qb.burn_should_fire() is False


def test_burn_should_fire_safe_by_default_when_quota_unknown(monkeypatch):
    """If we haven't observed the quota yet, refuse to burn — never probe blind."""
    _force_phase3(monkeypatch)
    qb._quota_remaining = None
    assert qb.burn_should_fire() is False


def test_burn_should_fire_off_when_paused(monkeypatch):
    """Operator pause must dominate over burn-window time."""
    monkeypatch.setattr(qb, "harvester_enabled", lambda: False)
    _force_phase3(monkeypatch)
    qb._quota_remaining = 800
    assert qb.burn_should_fire() is False


def test_update_quota_captures_per_minute_remaining():
    qb.update_quota(7400, per_minute_remaining=250)
    assert qb.quota_remaining() == 7400
    assert qb.per_minute_remaining() == 250


def test_budget_summary_includes_new_fields(monkeypatch):
    _force_phase2(monkeypatch)
    qb._quota_remaining = 5000
    qb._per_minute_remaining = 280
    s = qb.budget_summary()
    for key in (
        "quota_remaining",
        "per_minute_remaining",
        "live_reserve_floor",
        "burn_buffer",
        "burn_window_minutes",
        "daily_quota",
        "burn_should_fire",
    ):
        assert key in s, f"summary missing {key}"
    assert s["live_reserve_floor"] == 2500
    assert s["burn_buffer"] == 100
    assert s["burn_window_minutes"] == 120
    assert s["daily_quota"] == 75000
    assert s["per_minute_remaining"] == 280
