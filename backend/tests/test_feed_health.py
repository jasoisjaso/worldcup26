"""Feed-health registry: staleness and degraded-flag behaviour."""
from datetime import datetime, timezone, timedelta

from backend.data import feed_health


def test_unregistered_feed_record_is_noop():
    # Recording a feed that was never registered must not raise or invent an entry.
    feed_health.record("nope_not_registered_xyz")
    assert "nope_not_registered_xyz" not in feed_health.snapshot()["feeds"]


def test_never_run_is_fresh_within_boot_grace():
    # A freshly-deployed scheduled job has not fired yet; it must not read as stale
    # immediately or every deploy would show false-degraded.
    feed_health.register("fh_test_neverrun", "Never run", 30)
    feed = feed_health.snapshot()["feeds"]["fh_test_neverrun"]
    assert feed["last_success"] is None
    assert feed["stale"] is False


def test_never_run_is_stale_past_boot_grace():
    feed_health.register("fh_test_neverrun_old", "Never run old", 10)  # 10*3 = 30 min grace
    # Pretend the process started well before its job should have first fired.
    feed_health._STARTED_AT = datetime.now(timezone.utc) - timedelta(minutes=45)
    snap = feed_health.snapshot()
    feed = snap["feeds"]["fh_test_neverrun_old"]
    assert feed["stale"] is True
    assert "fh_test_neverrun_old" in snap["degraded"]
    assert snap["all_fresh"] is False
    # Restore so other tests are not affected by the backdated start.
    feed_health._STARTED_AT = datetime.now(timezone.utc)


def test_fresh_after_record():
    feed_health.register("fh_test_fresh", "Fresh", 30)
    feed_health.record("fh_test_fresh")
    feed = feed_health.snapshot()["feeds"]["fh_test_fresh"]
    assert feed["stale"] is False
    assert feed["age_minutes"] is not None and feed["age_minutes"] < 1


def test_goes_stale_past_grace_multiple():
    feed_health.register("fh_test_stale", "Stale", 10)  # 10-min interval, 3x grace = 30 min
    # Backdate the last success past the grace window.
    feed_health._FEEDS["fh_test_stale"]["last_success"] = (
        datetime.now(timezone.utc) - timedelta(minutes=45)
    )
    feed = feed_health.snapshot()["feeds"]["fh_test_stale"]
    assert feed["stale"] is True

    # Inside the grace window it is still fresh.
    feed_health._FEEDS["fh_test_stale"]["last_success"] = (
        datetime.now(timezone.utc) - timedelta(minutes=15)
    )
    assert feed_health.snapshot()["feeds"]["fh_test_stale"]["stale"] is False
