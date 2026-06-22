"""Regression: missed penalties must NOT be counted as goals.

Pre-2026-06-23, rebuild_player_tournament_stats had three branches:
  detail == "Own Goal"   -> own_goals++
  detail == "Penalty"    -> penalty_goals++ AND goals++
  else                   -> goals++

The catch-all else was the bug. api-football emits *missed* penalties with
type="Goal", detail="Missed Penalty" (yes, type=Goal even though it isn't),
which slipped past the explicit conditions and incremented goals.

That meant when Messi missed his penalty vs Austria the leaderboard credited
him a goal. These tests pin the corrected behaviour: a missed pen counts
toward penalty_attempts and penalty_misses but never toward goals; a scored
pen counts toward both penalty_attempts and goals; and shootout pens are
bucketed separately from regulation pens so a shootout-skill signal isn't
diluted by regulation pen-takers.
"""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture()
def db_env(monkeypatch):
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "pen_test.db")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("WC26_STATE_DIR", tmp)
    monkeypatch.setenv("WC26_HARVEST", "0")

    import importlib
    import backend.db.session as session
    importlib.reload(session)
    from backend.db import migrate

    session.init_db()
    migrate.run_migrations()
    return session


def _add_event(db, MatchEvent, **kw):
    defaults = {
        "match_id": "TEST_MATCH",
        "api_fixture_id": 9001,
        "elapsed": 50,
        "extra": 0,
        "team_id": 26,
        "team_name": "Argentina",
    }
    defaults.update(kw)
    db.add(MatchEvent(**defaults))


def test_missed_penalty_not_counted_as_goal(db_env):
    """The exact Messi-vs-Austria scenario: 1 scored pen earlier in tournament,
    1 missed pen tonight. Pre-fix this would show 2 goals. Post-fix: 1 goal,
    2 attempts, 1 miss."""
    import backend.data.persistence as persistence
    from backend.db.models import MatchEvent, PlayerTournamentStats

    db = db_env.SessionLocal()
    # Scored pen, earlier match
    _add_event(db, MatchEvent, type="Goal", detail="Penalty",
               player_id=2782, player_name="L. Messi", elapsed=40)
    # Missed pen, tonight
    _add_event(db, MatchEvent, type="Goal", detail="Missed Penalty",
               player_id=2782, player_name="L. Messi", elapsed=63)
    db.commit()

    n = persistence.rebuild_player_tournament_stats(db, tournament="WC2026")
    db.commit()
    assert n >= 1

    row = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == 2782)
        .first()
    )
    assert row is not None, "rebuild should write a row for Messi"
    # Messi has 1 actual goal (the scored pen), NOT 2.
    assert row.goals == 1
    assert row.penalty_goals == 1
    assert row.penalty_attempts == 2
    assert row.penalty_misses == 1
    db.close()


def test_open_play_goal_unaffected(db_env):
    """Sanity: a normal open-play goal still counts as a goal and doesn't
    touch the penalty counters."""
    import backend.data.persistence as persistence
    from backend.db.models import MatchEvent, PlayerTournamentStats

    db = db_env.SessionLocal()
    _add_event(db, MatchEvent, type="Goal", detail="Normal Goal",
               player_id=909, player_name="Test Striker")
    db.commit()
    persistence.rebuild_player_tournament_stats(db, tournament="WC2026")
    db.commit()

    row = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == 909)
        .first()
    )
    assert row.goals == 1
    assert row.penalty_attempts == 0
    assert row.penalty_goals == 0
    assert row.penalty_misses == 0
    db.close()


def test_shootout_pens_bucketed_separately(db_env):
    """A shootout penalty (marked via comments="Penalty Shootout" or
    elapsed > 120) must increment the shootout buckets so the regulation
    conversion rate isn't polluted."""
    import backend.data.persistence as persistence
    from backend.db.models import MatchEvent, PlayerTournamentStats

    db = db_env.SessionLocal()
    # Regulation pen, scored, minute 70
    _add_event(db, MatchEvent, type="Goal", detail="Penalty",
               player_id=11, player_name="Reg Kicker", elapsed=70)
    # Shootout pen, scored, elapsed=121 (no comment)
    _add_event(db, MatchEvent, type="Goal", detail="Penalty",
               player_id=11, player_name="Reg Kicker", elapsed=121)
    # Shootout pen, missed, with explicit comment
    _add_event(db, MatchEvent, type="Goal", detail="Missed Penalty",
               player_id=11, player_name="Reg Kicker",
               elapsed=125, comments="Penalty Shootout")
    db.commit()

    persistence.rebuild_player_tournament_stats(db, tournament="WC2026")
    db.commit()

    row = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == 11)
        .first()
    )
    # Totals: 3 attempts, 1 miss, 2 scored pens (= goals = 2)
    assert row.penalty_attempts == 3
    assert row.penalty_misses == 1
    assert row.penalty_goals == 2
    assert row.goals == 2
    # Shootout split: 2 attempts (1 scored, 1 missed)
    assert row.shootout_penalty_goals == 1
    assert row.shootout_penalty_misses == 1
    db.close()


def test_own_goal_still_excluded(db_env):
    """Regression on the existing own-goal rule: must not count as a goal
    even after the missed-pen branch was added."""
    import backend.data.persistence as persistence
    from backend.db.models import MatchEvent, PlayerTournamentStats

    db = db_env.SessionLocal()
    _add_event(db, MatchEvent, type="Goal", detail="Own Goal",
               player_id=77, player_name="Unlucky Defender")
    db.commit()
    persistence.rebuild_player_tournament_stats(db, tournament="WC2026")
    db.commit()

    row = (
        db.query(PlayerTournamentStats)
        .filter(PlayerTournamentStats.player_id == 77)
        .first()
    )
    assert row.goals == 0
    assert row.own_goals == 1
    assert row.penalty_attempts == 0
    db.close()
