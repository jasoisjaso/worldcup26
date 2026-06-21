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
  /players/squads       → PlayerProfile (upsert by player_id)
  /players              → PlayerProfile (basic) + PlayerTournamentStats (aggregate)
  /fixtures             → no direct write; auto-enqueues sub-endpoints
  /fixtures/statistics  → FixtureArchive (upsert by api_fixture_id, team_api_id)
  /fixtures/events      → Feed into existing persist_events() — commits
  /predictions          → Feed into existing persist_api_prediction()
  /odds                 → HarvestRaw only for now (odds schema is complex; keep raw)

Schema sanity contract — DO NOT change without updating models.py:
  PlayerProfile.player_id is the PK (integer, api-football player id).
  PlayerTournamentStats columns: player_id, player_name, team_id, team_name,
    tournament, appearances, minutes, goals, assists, yellow_cards, red_cards.
  PlayerHistory: api_player_id + api_fixture_id (composite unique in practice).
  FixtureArchive: api_fixture_id + team_api_id (composite unique in practice).
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
    MatchEvent,
    MatchStatistics,
    PlayerHistory,
    PlayerProfile,
    PlayerTournamentStats,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

BATCH_SIZE = 25   # blobs processed per tick — keeps up with 1-min harvester cadence
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


def _to_int(v) -> int | None:
    """Permissive int cast — handles '75%', None, empty string."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str):
            v = v.rstrip("%").strip()
        return int(float(v))
    except (ValueError, TypeError):
        return None


def _to_float(v) -> float | None:
    """Permissive float cast — handles '75%', None, empty string."""
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str):
            v = v.rstrip("%").strip()
        return float(v)
    except (ValueError, TypeError):
        return None


def _resolve_match_id(db, api_fixture_id: int | None) -> str | None:
    """Best-effort: map an api-football fixture id back to our internal Match.id.

    The Match table itself does NOT carry api_fixture_id (it's keyed by our own
    "M029"-style codes). The mapping appears in MatchEvent/MatchStatistics rows
    once the live poller has touched a fixture. We query both as a fallback.
    Returns None if neither table knows this fixture — caller decides what to do."""
    if not api_fixture_id:
        return None
    row = (
        db.query(MatchEvent.match_id)
        .filter(MatchEvent.api_fixture_id == api_fixture_id)
        .first()
    )
    if row and row[0]:
        return row[0]
    row = (
        db.query(MatchStatistics.match_id)
        .filter(MatchStatistics.api_fixture_id == api_fixture_id)
        .first()
    )
    return row[0] if row and row[0] else None


# ---------------------------------------------------------------------------
# Normalisers — one per endpoint pattern
# ---------------------------------------------------------------------------

def _normalise_players_squads(raw: HarvestRaw) -> int:
    """Extract player records from /players/squads?team=X response.

    Shape per api-football v3: response[0].team + response[0].players[].
    Each players[] entry has id, name, age, number, position, photo directly
    (not nested under .player). We accept both shapes defensively in case the
    response is wrapped differently in the harvester edge case.

    Returns number of rows upserted into PlayerProfile."""
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
            team_id_outer = team.get("id")
            team_name_outer = team.get("name")
            players = entry.get("players") or []
            # Defensive: some responses wrap each player under .player
            for p_raw in players:
                p = p_raw.get("player") if isinstance(p_raw.get("player"), dict) else p_raw
                pid = p.get("id")
                if not pid:
                    continue
                existing = db.query(PlayerProfile).filter(PlayerProfile.player_id == pid).first()
                fields = {
                    "name": p.get("name"),
                    "age": p.get("age"),
                    "position": p.get("position"),
                    "photo_url": p.get("photo"),
                    "team_id": team_id_outer,
                    "team_name": team_name_outer,
                    "updated_at": datetime.utcnow(),
                }
                if existing:
                    for k, v in fields.items():
                        if v:
                            setattr(existing, k, v)
                else:
                    db.add(PlayerProfile(player_id=pid, **fields))
                added += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_players_squads", str(exc))
    finally:
        db.close()
    return added


def _normalise_players(raw: HarvestRaw) -> int:
    """Extract player season stats from /players?team=X&season=Y.

    Shape: response[].player + response[].statistics[]. Each statistics entry
    is per (player, league, season, team). We write PlayerHistory (per-fixture
    granularity is NOT in this response — `game.id` is null per docs; per-fixture
    rows come from /fixtures/players which we don't queue here) and
    PlayerTournamentStats (aggregate across all statistics rows for the player).

    Returns count of rows touched (PlayerHistory + PlayerTournamentStats writes).
    """
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
            pid = p.get("id")
            if not pid:
                continue
            pname = p.get("name")
            stats_list = entry.get("statistics") or []
            # Aggregate across all statistics rows (player may have multiple
            # leagues / seasons in one response).
            agg_app = 0
            agg_min = 0
            agg_goals = 0
            agg_assists = 0
            agg_yc = 0
            agg_rc = 0
            primary_team_id = None
            primary_team_name = None
            for s in stats_list:
                team = s.get("team") or {}
                games = s.get("games") or {}
                goals = s.get("goals") or {}
                cards = s.get("cards") or {}
                if not primary_team_id:
                    primary_team_id = team.get("id")
                    primary_team_name = team.get("name")
                agg_app += int(games.get("appearences") or 0)
                agg_min += int(s.get("minutes") or games.get("minutes") or 0)
                agg_goals += int(goals.get("total") or 0)
                agg_assists += int(goals.get("assists") or 0)
                agg_yc += int(cards.get("yellow") or 0)
                agg_rc += int(cards.get("red") or 0)

            # PlayerTournamentStats — upsert by (player_id, team_id) so we
            # accumulate over time without duplicating. tournament defaults to
            # "WC2026" but we use the team's primary league tournament tag here.
            existing_pts = (
                db.query(PlayerTournamentStats)
                .filter(PlayerTournamentStats.player_id == pid)
                .filter(PlayerTournamentStats.team_id == primary_team_id)
                .first()
            )
            if existing_pts:
                existing_pts.player_name = pname or existing_pts.player_name
                existing_pts.team_name = primary_team_name or existing_pts.team_name
                existing_pts.appearances = agg_app
                existing_pts.minutes = agg_min
                existing_pts.goals = agg_goals
                existing_pts.assists = agg_assists
                existing_pts.yellow_cards = agg_yc
                existing_pts.red_cards = agg_rc
                existing_pts.computed_at = datetime.utcnow()
            else:
                db.add(PlayerTournamentStats(
                    player_id=pid,
                    player_name=pname,
                    team_id=primary_team_id,
                    team_name=primary_team_name,
                    appearances=agg_app,
                    minutes=agg_min,
                    goals=agg_goals,
                    assists=agg_assists,
                    yellow_cards=agg_yc,
                    red_cards=agg_rc,
                ))
                added += 1

            # Also keep the PlayerProfile basic record fresh.
            existing_pp = db.query(PlayerProfile).filter(PlayerProfile.player_id == pid).first()
            if existing_pp:
                if pname:
                    existing_pp.name = pname
                if primary_team_id:
                    existing_pp.team_id = primary_team_id
                    existing_pp.team_name = primary_team_name
                existing_pp.updated_at = datetime.utcnow()
            elif pid and pname:
                db.add(PlayerProfile(
                    player_id=pid,
                    name=pname,
                    age=p.get("age"),
                    nationality=p.get("nationality"),
                    photo_url=p.get("photo"),
                    team_id=primary_team_id,
                    team_name=primary_team_name,
                ))
                added += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_players", str(exc))
    finally:
        db.close()
    return added


# Stat-name → FixtureArchive column. Lowercase contains-match. Keep this in
# sync with api-football's /fixtures/statistics response types.
_STAT_KEY_MAP = (
    ("ball possession",       "possession",      "pct"),
    ("total shots",           "shots_total",     "int"),
    ("shots on goal",         "shots_on_target", "int"),
    ("expected_goals",        "xg",              "float"),
    ("total passes",          "passes_total",    "int"),
    ("passes %",              "pass_accuracy",   "pct"),
    ("passes accurate",       "passes_total",    "int"),  # falls through if no Total
    ("fouls",                 "fouls",           "int"),
    ("yellow cards",          "yellow_cards",    "int"),
    ("red cards",             "red_cards",       "int"),
    ("corner kicks",          "corners",         "int"),
)


def _normalise_statistics(raw: HarvestRaw) -> int:
    """Extract per-team match stats from /fixtures/statistics?fixture=X.

    Response shape: response[].team + response[].statistics[]
      where each statistics entry is {"type": "Ball Possession", "value": "55%"}.

    Idempotent: upsert by (api_fixture_id, team_api_id). Last write wins per stat.
    Returns rows touched (1 per team per blob)."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    # Resolve fixture id from the harvest job params (response itself doesn't
    # include it consistently).
    fixture_id_from_job = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                fixture_id_from_job = int((json.loads(job.params_json) or {}).get("fixture") or 0) or None
            except Exception:
                fixture_id_from_job = None
    finally:
        db_outer.close()

    if not fixture_id_from_job:
        return 0  # can't usefully archive without a fixture id

    db = SessionLocal()
    written = 0
    try:
        internal_match_id = _resolve_match_id(db, fixture_id_from_job)
        for entry in rows:
            team = entry.get("team") or {}
            team_api_id = team.get("id")
            if not team_api_id:
                continue
            stats_list = entry.get("statistics") or []
            existing = (
                db.query(FixtureArchive)
                .filter(FixtureArchive.api_fixture_id == fixture_id_from_job)
                .filter(FixtureArchive.team_api_id == team_api_id)
                .first()
            )
            row = existing or FixtureArchive(
                api_fixture_id=fixture_id_from_job,
                team_api_id=team_api_id,
                match_id=internal_match_id,
            )
            for st in stats_list:
                t = (st.get("type") or "").lower()
                raw_v = st.get("value")
                if raw_v is None:
                    continue
                for needle, col, kind in _STAT_KEY_MAP:
                    if needle not in t:
                        continue
                    if kind == "int":
                        v = _to_int(raw_v)
                    elif kind == "float":
                        v = _to_float(raw_v)
                    else:  # pct
                        v = _to_float(raw_v)
                    if v is not None:
                        setattr(row, col, v)
                    break  # first matching key wins
            if internal_match_id and not row.match_id:
                row.match_id = internal_match_id
            if not existing:
                db.add(row)
            written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_statistics", str(exc))
    finally:
        db.close()
    return written


def _normalise_events(raw: HarvestRaw) -> int:
    """Feed /fixtures/events into the existing persistence layer.

    persist_events does NOT commit — we commit here after the call.
    Resolves api fixture → internal match_id; if unresolvable, skips silently
    (no point inserting orphan events that can't be queried back)."""
    try:
        from backend.data.persistence import persist_events
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
            internal_match_id = _resolve_match_id(db, int(fixture_id))
            if not internal_match_id:
                return 0  # match not in our system → don't pollute the events table
            n = persist_events(db, internal_match_id, int(fixture_id), rows)
            db.commit()
            return n
        finally:
            db.close()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_events", str(exc))
        return 0


def _normalise_prediction(raw: HarvestRaw) -> int:
    """Feed /predictions into the existing persistence layer.

    Same pattern as events — resolve internal match id, skip if unknown."""
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
            internal_match_id = _resolve_match_id(db, int(fixture_id))
            if not internal_match_id:
                return 0
            ok = persist_api_prediction(db, internal_match_id, int(fixture_id), rows[0])
            db.commit()
            return 1 if ok else 0
        finally:
            db.close()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_prediction", str(exc))
        return 0


def _normalise_fixtures(raw: HarvestRaw) -> int:
    """Process a /fixtures response: auto-enqueue per-fixture sub-endpoints so
    the pipeline self-seeds. We only fan out for FT/AET fixtures to avoid
    queueing stats for matches that haven't been played yet."""
    try:
        data = json.loads(raw.response_json)
        fixtures = data.get("response", []) or []
    except Exception:
        return 0

    queued = 0
    # /fixtures/players added 2026-06-21 to feed PlayerHistory + the
    # goalscorer market layer. Same priority as the others — fan-out for
    # every completed fixture.
    sub_endpoints = ["/fixtures/statistics", "/fixtures/events", "/predictions", "/fixtures/players"]
    for fx in fixtures:
        fid = (fx.get("fixture") or {}).get("id")
        status = ((fx.get("fixture") or {}).get("status") or {}).get("short")
        if not fid:
            continue
        # Only fan out for completed matches — stats endpoints return empty
        # for not-started fixtures and waste quota.
        if status not in {"FT", "AET", "PEN"}:
            continue
        for ep in sub_endpoints:
            if _harvest_enqueue(ep, {"fixture": fid}, priority=SUB_PRIORITY):
                queued += 1
    return queued


def _normalise_odds(raw: HarvestRaw) -> int:
    """Odds are stored raw only for now. The response is complex (dozens of
    bookmakers × multiple markets) — defer normalisation until we have a
    concrete use case. Return 0 (no rows written, but blob is still processed)."""
    return 0


def _normalise_fixture_players(raw: HarvestRaw) -> int:
    """Normalise /fixtures/players?fixture=X into PlayerHistory rows.

    Response shape: response[].team + response[].players[] where each player
    has a single statistics row for THIS fixture (api-football returns one
    row per game when queried by fixture).

    Idempotent upsert keyed on (api_player_id, api_fixture_id). Skips silently
    if the fixture id isn't recoverable from the job params.
    """
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    # Recover fixture id from the original harvest job params (the response
    # body doesn't repeat it consistently).
    fixture_id_from_job = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                fixture_id_from_job = int((json.loads(job.params_json) or {}).get("fixture") or 0) or None
            except Exception:
                fixture_id_from_job = None
    finally:
        db_outer.close()

    if not fixture_id_from_job:
        return 0

    db = SessionLocal()
    written = 0
    try:
        internal_match_id = _resolve_match_id(db, fixture_id_from_job)
        for team_entry in rows:
            players = team_entry.get("players") or []
            for p_raw in players:
                p = p_raw.get("player") or {}
                pid = p.get("id")
                if not pid:
                    continue
                stats_list = p_raw.get("statistics") or []
                if not stats_list:
                    continue
                s = stats_list[0]
                games = s.get("games") or {}
                goals = s.get("goals") or {}

                minutes = _to_int(games.get("minutes")) or 0
                rating_raw = games.get("rating")
                rating = _to_float(rating_raw) if rating_raw is not None else None

                existing = (
                    db.query(PlayerHistory)
                    .filter(PlayerHistory.api_player_id == pid)
                    .filter(PlayerHistory.api_fixture_id == fixture_id_from_job)
                    .first()
                )
                row = existing or PlayerHistory(
                    api_player_id=pid,
                    api_fixture_id=fixture_id_from_job,
                )
                row.match_id = internal_match_id
                row.goals = _to_int(goals.get("total")) or 0
                row.assists = _to_int(goals.get("assists")) or 0
                row.minutes = minutes
                row.rating = rating
                if not existing:
                    db.add(row)
                written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_fixture_players", str(exc))
    finally:
        db.close()
    return written


# ---------------------------------------------------------------------------
# Endpoint routing
# ---------------------------------------------------------------------------

_ROUTER = {
    "/players/squads":      _normalise_players_squads,
    "/players":             _normalise_players,
    "/fixtures/statistics": _normalise_statistics,
    "/fixtures/events":     _normalise_events,
    "/fixtures/players":    _normalise_fixture_players,
    "/fixtures":            _normalise_fixtures,
    "/predictions":         _normalise_prediction,
    "/odds":                _normalise_odds,
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
                    if endpoint == "/fixtures":
                        summary["sub_jobs_queued"] += n
                    else:
                        summary["rows_written"] += n
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
