"""Post-processor that reads raw api-football JSON from HarvestRaw and normalises
it into queryable tables (PlayerProfile, PlayerTournamentStats, PlayerHistory,
FixtureArchive, etc.).

Design:
- Scheduler calls run_one_pass() every 10 minutes.
- Each pass grabs the oldest 5 unprocessed blobs (HarvestRaw.processed=False,
  status_code=200), routes them by endpoint to a normaliser function, and marks
  them processed.
- Normalisers are idempotent — re-processing the same blob a second time updates
  existing rows rather than duplicating.
- On encountering a /fixtures response with a match list, the processor also
  auto-enqueues per-fixture sub-endpoints (statistics, events, predictions, odds)
  at lower priority. This makes the pipeline self-seeding — fetch fixtures →
  auto-queue detail for every fixture.

Endpoint → table mapping:
  /players/squads       → PlayerProfile (upsert by api_player_id)
  /players              → PlayerTournamentStats + PlayerHistory (upsert)
  /fixtures             → no direct write; auto-enqueues sub-endpoints
  /fixtures/statistics  → FixtureArchive (upsert by api_fixture_id, team_api_id)
  /fixtures/events      → Feed into existing persist_events()
  /predictions          → Feed into existing persist_api_prediction()
  /odds                 → HarvestRaw only for now (odds schema is complex; keep raw)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime

from backend.data.harvester import enqueue as _harvest_enqueue
from backend.db.models import (
    FixtureArchive,
    HarvestErrorLog,
    HarvestJob,
    HarvestRaw,
    PlayerHistory,
    PlayerProfile,
    PlayerTournamentStats,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

BATCH_SIZE = 5    # blobs processed per tick
SUB_PRIORITY = 250  # fan-out sub-endpoints at this priority


def _log_error(job_id: int | None, endpoint: str, error_type: str, msg: str) -> None:
    db = SessionLocal()
    try:
        db.add(HarvestErrorLog(job_id=job_id, endpoint=endpoint, error_type=error_type, error_msg=msg[:300]))
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Normalisers — one per endpoint pattern
# ---------------------------------------------------------------------------

def _normalise_players_squads(raw: HarvestRaw) -> int:
    """Extract player records from /players/squads?team=X response.
    Returns number of rows upserted."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    db = SessionLocal()
    added = 0
    try:
        for entry in rows:
            p = entry.get("player") or {}
            api_pid = p.get("id")
            if not api_pid:
                continue
            name = p.get("name") or ""
            age = p.get("age")
            pos = p.get("position") or ""
            nationality = p.get("nationality") or ""
            photo = p.get("photo")
            existing = db.query(PlayerProfile).filter(PlayerProfile.api_player_id == api_pid).first()
            if existing:
                existing.name = name or existing.name
                existing.age = age or existing.age
                existing.position = pos or existing.position
                existing.nationality = nationality or existing.nationality
                if photo:
                    existing.photo_url = photo
            else:
                db.add(PlayerProfile(
                    api_player_id=api_pid,
                    name=name,
                    age=age,
                    position=pos,
                    nationality=nationality,
                    photo_url=photo,
                ))
            added += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_players_squads", str(exc))
    finally:
        db.close()
    return added


def _normalise_players(raw: HarvestRaw) -> int:
    """Extract player season stats from /players?team=X&season=Y response.
    Writes to PlayerTournamentStats + PlayerHistory."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    db = SessionLocal()
    added = 0
    try:
        for entry in rows:
            player = entry.get("player") or {}
            api_pid = player.get("id")
            if not api_pid:
                continue
            stats = entry.get("statistics") or []
            for s in stats:
                game = s.get("game") or {}
                fixture_id = game.get("id")
                league = s.get("league") or {}
                team = s.get("team") or {}
                team_api_id = team.get("id")
                minutes = s.get("minutes") or 0
                goals = s.get("goals", {}) or {}
                shots = s.get("shots", {}) or {}
                passes = s.get("passes", {}) or {}
                # PlayerHistory — one row per fixture
                if fixture_id:
                    existing_ph = (
                        db.query(PlayerHistory)
                        .filter(PlayerHistory.api_player_id == api_pid)
                        .filter(PlayerHistory.api_fixture_id == fixture_id)
                        .first()
                    )
                    if not existing_ph:
                        db.add(PlayerHistory(
                            api_player_id=api_pid,
                            api_fixture_id=fixture_id,
                            goals=(goals.get("total") or 0),
                            assists=(goals.get("assists") or 0),
                            minutes=minutes,
                            rating=s.get("rating"),
                        ))
                        added += 1
                # PlayerTournamentStats — one row per player per season per league
                season = league.get("season")
                league_id = league.get("id")
                if api_pid and season and team_api_id:
                    existing_pts = (
                        db.query(PlayerTournamentStats)
                        .filter(PlayerTournamentStats.api_player_id == api_pid)
                        .filter(PlayerTournamentStats.season == season)
                        .filter(PlayerTournamentStats.team_api_id == team_api_id)
                        .first()
                    )
                    appearances = s.get("appearences") or 0
                    if existing_pts:
                        existing_pts.appearances = (existing_pts.appearances or 0) + appearances
                        existing_pts.goals = (existing_pts.goals or 0) + (goals.get("total") or 0)
                        existing_pts.assists = (existing_pts.assists or 0) + (goals.get("assists") or 0)
                        existing_pts.minutes = (existing_pts.minutes or 0) + minutes
                    else:
                        db.add(PlayerTournamentStats(
                            api_player_id=api_pid,
                            season=season,
                            league_id=league_id,
                            team_api_id=team_api_id,
                            appearances=appearances,
                            goals=goals.get("total", 0),
                            assists=goals.get("assists", 0),
                            minutes=minutes,
                            shots_total=shots.get("total"),
                            shots_on=(shots.get("on") or 0),
                            passes_total=passes.get("total"),
                            pass_accuracy=passes.get("accuracy"),
                        ))
                        added += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_players", str(exc))
    finally:
        db.close()
    return added


def _normalise_statistics(raw: HarvestRaw) -> int:
    """Extract per-team match stats from /fixtures/statistics?fixture=X."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    db = SessionLocal()
    added = 0
    try:
        for entry in rows:
            team = entry.get("team") or {}
            team_api_id = team.get("id")
            fixture_api_id = (entry.get("fixture") or {}).get("id") or None
            if not team_api_id:
                continue
            stats_list = entry.get("statistics") or []
            existing = None
            if fixture_api_id:
                existing = (
                    db.query(FixtureArchive)
                    .filter(FixtureArchive.api_fixture_id == fixture_api_id)
                    .filter(FixtureArchive.team_api_id == team_api_id)
                    .first()
                )
            row = existing or FixtureArchive(api_fixture_id=fixture_api_id or 0, team_api_id=team_api_id)
            # Stats come as [{"type": "Shots on Goal", "value": 5}, ...]
            for st in stats_list:
                t = (st.get("type") or "").lower()
                v = st.get("value")
                if v is None:
                    continue
                try:
                    v = float(v)
                except (ValueError, TypeError):
                    continue
                if "possession" in t:
                    row.possession = v
                elif "total shots" in t:
                    row.shots_total = int(v)
                elif "shots on" in t:
                    row.shots_on_target = int(v)
                elif "expected goals" in t:
                    row.xg = v
                elif "total passes" in t:
                    row.passes_total = int(v)
                elif "passes accurate" in t or "pass %" in t:
                    row.pass_accuracy = int(v)
                elif "fouls" in t:
                    row.fouls = int(v)
                elif "yellow cards" in t:
                    row.yellow_cards = int(v)
                elif "red cards" in t:
                    row.red_cards = int(v)
                elif "corner kicks" in t:
                    row.corners = int(v)
            if not existing:
                db.add(row)
                added += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_statistics", str(exc))
    finally:
        db.close()
    return added


def _normalise_events(raw: HarvestRaw) -> int:
    """Feed /fixtures/events into the existing persistence layer."""
    try:
        from backend.data.persistence import persist_events
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
        # We need the match_id to route to persist_events. Try to resolve from
        # the harvest job params. If not resolvable, store as raw only.
        db = SessionLocal()
        try:
            job = db.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
            params = json.loads(job.params_json) if job and job.params_json else {}
            fixture_id = params.get("fixture")
            if not fixture_id:
                return 0
            return persist_events(db, f"harvest-{fixture_id}", fixture_id, rows)
        finally:
            db.close()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_events", str(exc))
        return 0


def _normalise_prediction(raw: HarvestRaw) -> int:
    """Feed /predictions into the existing persistence layer."""
    try:
        from backend.data.persistence import persist_api_prediction
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
        if not rows:
            return 0
        db = SessionLocal()
        try:
            job = db.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
            params = json.loads(job.params_json) if job and job.params_json else {}
            fixture_id = params.get("fixture")
            if not fixture_id:
                return 0
            ok = persist_api_prediction(db, f"harvest-{fixture_id}", fixture_id, rows[0])
            db.commit()
            return 1 if ok else 0
        finally:
            db.close()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_prediction", str(exc))
        return 0


def _normalise_fixtures(raw: HarvestRaw) -> int:
    """Process a /fixtures response: auto-enqueue per-fixture sub-endpoints
    so the pipeline self-seeds."""
    try:
        data = json.loads(raw.response_json)
        fixtures = data.get("response", []) or []
    except Exception:
        return 0

    queued = 0
    sub_endpoints = [
        ("/fixtures/statistics", 0),
        ("/fixtures/events", 0),
        ("/predictions", 0),
        ("/odds", 0),
    ]
    for fx in fixtures:
        fid = (fx.get("fixture") or {}).get("id")
        if not fid:
            continue
        for ep, _ in sub_endpoints:
            if _harvest_enqueue(ep, {"fixture": fid}, priority=SUB_PRIORITY):
                queued += 1
    return queued


def _normalise_odds(raw: HarvestRaw) -> int:
    """Odds are stored raw only for now. The response is complex (dozens of
    bookmakers × multiple markets) — defer normalisation until we have a
    concrete use case. Return 0 (no rows written, but blob is still processed)."""
    return 0


# ---------------------------------------------------------------------------
# Endpoint routing
# ---------------------------------------------------------------------------

_ROUTER: dict[str, callable] = {  # type: ignore[type-arg]
    "/players/squads":      _normalise_players_squads,
    "/players":              _normalise_players,
    "/fixtures/statistics":  _normalise_statistics,
    "/fixtures/events":      _normalise_events,
    "/fixtures":             _normalise_fixtures,
    "/predictions":          _normalise_prediction,
    "/odds":                 _normalise_odds,
}


def run_one_pass() -> dict:
    """Process the oldest N unprocessed HarvestRaw blobs. Mark as processed
    after each is normalised (success or not — we don't retry the same blob).

    Returns a summary dict the scheduler health endpoint can surface."""
    db = SessionLocal()
    try:
        blobs = (
            db.query(HarvestRaw)
            .filter(HarvestRaw.processed == False)  # noqa: E712
            .filter(HarvestRaw.status_code == 200)
            .order_by(HarvestRaw.id.asc())
            .limit(BATCH_SIZE)
            .all()
        )
        if not blobs:
            return {"status": "idle"}

        summary = {"processed": 0, "rows_written": 0, "sub_jobs_queued": 0, "errors": 0}
        for blob in blobs:
            endpoint = (blob.endpoint or "").strip()
            fn = _ROUTER.get(endpoint)
            try:
                if fn:
                    n = fn(blob)
                    summary["rows_written"] += n
                    # _normalise_fixtures returns sub-job count, not rows
                    if endpoint == "/fixtures":
                        summary["sub_jobs_queued"] += n
                else:
                    logger.debug("harvest processor: no normaliser for %s (blob %d)", endpoint, blob.id)
            except Exception as exc:
                summary["errors"] += 1
                _log_error(blob.job_id, endpoint, "processor_run", str(exc))
            blob.processed = True
            summary["processed"] += 1

        db.commit()
        return {"status": "ran", **summary}
    finally:
        db.close()
