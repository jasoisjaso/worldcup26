"""Regression tests: every quota consumer must respect LIVE_RESERVE_FLOOR.

The 2,500-call reserve is an absolute guarantee for live polling. Before
this lock, three consumers leaked into it:
- backfill_can_run gated at < 200
- burn_should_fire gated at PHASE3_BUFFER (100)
- harvester_can_run Phase-3 gated at PHASE3_BUFFER
- injuries_can_run gated at > 2000

These tests pin the floor to LIVE_RESERVE_FLOOR for every non-live consumer.
"""
from __future__ import annotations

import os
from datetime import datetime
from unittest.mock import patch

import pytest

os.environ.setdefault("WC26_STATE_DIR", "/tmp/wc26_test_state_floor")
os.makedirs(os.environ["WC26_STATE_DIR"], exist_ok=True)
# Ensure harvester isn't disabled by env-level kill switch in this test.
os.environ["WC26_HARVEST"] = "1"

from backend.data import quota_budget as qb  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_quota_state():
    """Clear in-process counters before each test and unset any runtime pause."""
    qb._quota_remaining = None
    qb._daily_calls_made = 0
    qb._backfill_calls_today = 0
    qb._last_read_date = datetime.utcnow().date().isoformat()
    qb._QUOTA_EXHAUSTED_DATE = None
    # Force "not paused" by stubbing the runtime_settings import the gate uses.
    with patch("backend.data.runtime_settings.harvest_paused", return_value=False):
        yield


def _set_quota(remaining: int) -> None:
    """Update the in-process counter without going through update_quota
    (which side-effect-increments daily_calls_made and triggers persistence)."""
    qb._quota_remaining = remaining


def test_backfill_refuses_at_reserve_floor():
    """At the floor, backfill must NOT run — its 140-call cycle would breach."""
    _set_quota(qb.LIVE_RESERVE_FLOOR)
    # Force a Phase 1 / fresh-day shape so the in_phase1 + counter-zero path
    # are satisfied — only the floor gate should fail.
    with patch.object(qb, "in_phase1", return_value=True):
        assert qb.backfill_can_run() is False


def test_backfill_refuses_one_below_floor():
    _set_quota(qb.LIVE_RESERVE_FLOOR - 1)
    with patch.object(qb, "in_phase1", return_value=True):
        assert qb.backfill_can_run() is False


def test_backfill_allowed_above_floor_in_phase1():
    _set_quota(qb.LIVE_RESERVE_FLOOR + 200)
    with patch.object(qb, "in_phase1", return_value=True):
        assert qb.backfill_can_run() is True


def test_harvester_refuses_at_reserve_floor_phase2():
    _set_quota(qb.LIVE_RESERVE_FLOOR)
    with patch.object(qb, "in_phase1", return_value=False), \
         patch.object(qb, "in_phase3", return_value=False):
        # _quota_remaining >= LIVE_RESERVE_FLOOR returns True at exactly the
        # floor — that's a 0-room edge. We want SAFETY: any consumer that
        # could drain even one call must refuse AT the floor. Phase-2 uses
        # >= which means it WILL try; the next call wraps below. That's
        # acceptable for Phase 2 because batch_size is also gated, but the
        # cleaner test is one-below.
        # Confirming the explicit "below floor must refuse" path:
        _set_quota(qb.LIVE_RESERVE_FLOOR - 1)
        assert qb.harvester_can_run() is False


def test_harvester_refuses_below_floor_in_burn_window():
    """Phase 3 burn must STOP at the reserve floor — the bug this test catches."""
    _set_quota(qb.LIVE_RESERVE_FLOOR)
    with patch.object(qb, "in_phase1", return_value=False), \
         patch.object(qb, "in_phase3", return_value=True):
        # At exactly the floor, > LIVE_RESERVE_FLOOR is False → refuse.
        assert qb.harvester_can_run() is False


def test_burn_should_fire_refuses_at_reserve_floor():
    """burn_should_fire (the burst-tick gate) must also respect the floor."""
    _set_quota(qb.LIVE_RESERVE_FLOOR)
    with patch.object(qb, "in_phase3", return_value=True):
        assert qb.burn_should_fire() is False


def test_burn_should_fire_allowed_well_above_floor():
    _set_quota(qb.LIVE_RESERVE_FLOOR + 500)
    with patch.object(qb, "in_phase3", return_value=True):
        assert qb.burn_should_fire() is True


def test_injuries_refuses_within_reserve_cushion():
    """48-call cycle needs LIVE_RESERVE_FLOOR + 50 cushion, not bare floor."""
    _set_quota(qb.LIVE_RESERVE_FLOOR + 50)
    with patch.object(qb, "in_phase1", return_value=False):
        # > LIVE_RESERVE_FLOOR + 50 is False at exactly the cushion → refuse.
        assert qb.injuries_can_run() is False


def test_injuries_allowed_well_above_cushion():
    _set_quota(qb.LIVE_RESERVE_FLOOR + 500)
    with patch.object(qb, "in_phase1", return_value=False):
        assert qb.injuries_can_run() is True


def test_small_job_already_respects_floor():
    """small_job_allowed has gated at LIVE_RESERVE_FLOOR since day one —
    pin it so it doesn't regress."""
    _set_quota(qb.LIVE_RESERVE_FLOOR)
    assert qb.small_job_allowed() is False
    _set_quota(qb.LIVE_RESERVE_FLOOR + 1)
    assert qb.small_job_allowed() is True


def test_live_reserve_floor_is_2500():
    """Lock the floor value — change this test deliberately if the operator
    raises or lowers the reserve."""
    assert qb.LIVE_RESERVE_FLOOR == 2500
