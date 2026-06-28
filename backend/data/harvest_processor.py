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
    CoachProfile,
    FixtureArchive,
    FixtureLineup,
    HarvestErrorLog,
    HarvestJob,
    HarvestRaw,
    MatchEvent,
    MatchStatistics,
    PlayerHistory,
    PlayerProfile,
    PlayerSeasonStats,
    PlayerSidelined,
    PlayerTournamentStats,
    PlayerTransfer,
    StandingsHistory,
    TeamSeasonProfile,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

BATCH_SIZE = 500  # bumped 2026-06-28 — 60/pass left ~331K blobs unprocessed
                  # after group stage. 500/pass × 6 passes/h = 72K/day; the
                  # harvester adds ~15K/day so the queue drains while running.
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
    ("ball possession",       "possession",        "pct"),
    ("shots on goal",         "shots_on_target",   "int"),
    ("shots off goal",        "shots_off_target",  "int"),
    ("total shots",           "shots_total",       "int"),
    ("shots insidebox",       "shots_insidebox",   "int"),
    ("shots outsidebox",      "shots_outsidebox",  "int"),
    ("blocked shots",         "shots_blocked",     "int"),
    ("expected_goals",        "xg",                "float"),
    ("goals prevented",       "goals_prevented",   "float"),
    ("total passes",          "passes_total",      "int"),
    ("passes %",              "pass_accuracy",     "pct"),
    ("passes accurate",       "passes_total",      "int"),  # fallback
    ("fouls",                 "fouls",             "int"),
    ("yellow cards",          "yellow_cards",      "int"),
    ("red cards",             "red_cards",         "int"),
    ("corner kicks",          "corners",           "int"),
    ("offsides",              "offsides",          "int"),
    ("goalkeeper saves",      "goalkeeper_saves",  "int"),
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
    # /fixtures/lineups added 2026-06-21. Same fan-out pattern — enqueue
    # per-fixture sub-endpoints for every completed fixture.
    sub_endpoints = [
        "/fixtures/statistics", "/fixtures/events", "/predictions",
        "/fixtures/players", "/fixtures/lineups",
    ]

    # Also discover teams and enqueue team-level endpoints once per
    # (team, league, season). This auto-seeds /teams/statistics, /coachs,
    # and /sidelined without needing a separate manual seed pass.
    teams_seen: set[tuple[int, int, int]] = set()
    league_id = season = None

    for fx in fixtures:
        fid = (fx.get("fixture") or {}).get("id")
        status = ((fx.get("fixture") or {}).get("status") or {}).get("short")
        if not fid:
            continue
        if status not in {"FT", "AET", "PEN"}:
            continue
        for ep in sub_endpoints:
            if _harvest_enqueue(ep, {"fixture": fid}, priority=SUB_PRIORITY):
                queued += 1

        # Collect team IDs for auto-seeding team-level endpoints
        teams = fx.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        lg = fx.get("league") or {}
        if not league_id:
            league_id = lg.get("id")
        if not season:
            season = lg.get("season")
        for t in [home, away]:
            tid = t.get("id")
            if tid and league_id and season:
                teams_seen.add((int(tid), int(league_id), int(season)))

    # Auto-seed team-level endpoints for every discovered team
    for tid, lid, ssn in teams_seen:
        base = {"team": tid, "league": lid, "season": ssn}
        if _harvest_enqueue("/teams/statistics", base, priority=160):
            queued += 1
        if _harvest_enqueue("/coachs", {"team": tid}, priority=250):
            queued += 1
        if _harvest_enqueue("/sidelined", {"team": tid}, priority=250):
            queued += 1
        if _harvest_enqueue("/transfers", {"team": tid}, priority=250):
            queued += 1

    return queued


def _normalise_odds(raw: HarvestRaw) -> int:
    """Odds are stored raw only for now. The response is complex (dozens of
    bookmakers × multiple markets) — defer normalisation until we have a
    concrete use case. Return 0 (no rows written, but blob is still processed)."""
    return 0


def _normalise_lineups(raw: HarvestRaw) -> int:
    """Normalise /fixtures/lineups?fixture=X into FixtureLineup rows.

    Response: [].startXI[].player + [].substitutes[].player with per-player
    stats (minutes, rating, shots, passes, tackles, etc.).
    """
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    fid = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                fid = int((json.loads(job.params_json) or {}).get("fixture") or 0) or None
            except Exception:
                fid = None
    finally:
        db_outer.close()

    if not fid:
        return 0

    db = SessionLocal()
    written = 0
    try:
        internal_id = _resolve_match_id(db, fid)
        for team_data in rows:
            team = team_data.get("team") or {}
            team_id = team.get("id")
            team_name = team.get("name")

            for section, is_starter in [("startXI", True), ("substitutes", False)]:
                players = team_data.get(section) or []
                for entry in players:
                    p = (entry.get("player") or {}) if isinstance(entry, dict) else {}
                    pid = p.get("id")
                    if not pid:
                        continue
                    name = p.get("name")
                    number = p.get("number")
                    pos = p.get("pos")
                    grid = p.get("grid")

                    stats = (entry.get("statistics") or [{}])[0] if isinstance(entry, dict) else {}
                    games = stats.get("games") or {}
                    shots = stats.get("shots") or {}
                    passes = stats.get("passes") or {}
                    tackles = stats.get("tackles") or {}
                    dribbles = stats.get("dribbles") or {}
                    duels = stats.get("duels") or {}

                    existing = (
                        db.query(FixtureLineup)
                        .filter(FixtureLineup.api_fixture_id == fid)
                        .filter(FixtureLineup.team_api_id == team_id)
                        .filter(FixtureLineup.player_api_id == pid)
                        .first()
                    )
                    row = existing or FixtureLineup(
                        api_fixture_id=fid, team_api_id=team_id, player_api_id=pid,
                    )
                    row.match_id = internal_id
                    row.team_name = team_name
                    row.player_name = name
                    row.player_number = _to_int(number)
                    row.position = pos
                    row.is_starter = is_starter
                    row.grid_position = grid
                    row.minutes_played = _to_int(games.get("minutes")) or 0
                    row.rating = _to_float(games.get("rating"))
                    row.shots_total = _to_int(shots.get("total"))
                    row.shots_on = _to_int(shots.get("on"))
                    row.passes_total = _to_int(passes.get("total"))
                    row.passes_accuracy = _to_int(passes.get("accuracy"))
                    row.tackles_total = _to_int(tackles.get("total"))
                    row.dribbles_attempts = _to_int(dribbles.get("attempts"))
                    row.duels_won = _to_int(duels.get("won"))
                    if not existing:
                        db.add(row)
                    written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_lineups", str(exc))
    finally:
        db.close()
    return written


def _normalise_standings(raw: HarvestRaw) -> int:
    """Normalise /standings?league=X&season=Y into StandingsHistory rows."""
    try:
        data = json.loads(raw.response_json)
        groups = data.get("response", []) or []
    except Exception:
        return 0

    # Recover league + season from job params
    league_id = season = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                p = json.loads(job.params_json) or {}
                league_id = p.get("league")
                season = p.get("season")
            except Exception:
                pass
    finally:
        db_outer.close()

    if not league_id or not season:
        return 0

    db = SessionLocal()
    written = 0
    try:
        for group in groups:
            gname = group.get("group") or group.get("name")
            for entry in group.get("standings") or group if isinstance(group.get("standings"), list) else []:
                if not isinstance(entry, dict):
                    continue
                team = entry.get("team") or {}
                tid = team.get("id")
                if not tid:
                    continue
                all_stats = entry.get("all") or {}

                existing = (
                    db.query(StandingsHistory)
                    .filter(StandingsHistory.league_id == league_id)
                    .filter(StandingsHistory.season == season)
                    .filter(StandingsHistory.team_api_id == tid)
                    .first()
                )
                row = existing or StandingsHistory(
                    league_id=league_id, season=season, team_api_id=tid,
                )
                row.team_name = team.get("name")
                row.rank = entry.get("rank") or 0
                row.points = entry.get("points") or 0
                row.goals_diff = entry.get("goalsDiff") or 0
                row.form = entry.get("form")
                row.matches_played = all_stats.get("played") or 0
                row.wins = all_stats.get("win") or 0
                row.draws = all_stats.get("draw") or 0
                row.losses = all_stats.get("lose") or 0
                row.goals_for = all_stats.get("goals", {}).get("for") or 0
                row.goals_against = all_stats.get("goals", {}).get("against") or 0
                row.group_name = group.get("name") if isinstance(group, dict) and group.get("name") != gname else gname
                row.status = entry.get("status")
                if not existing:
                    db.add(row)
                written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_standings", str(exc))
    finally:
        db.close()
    return written


def _normalise_coaches(raw: HarvestRaw) -> int:
    """Normalise /coachs?team=X into CoachProfile rows."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    team_id = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                team_id = (json.loads(job.params_json) or {}).get("team")
            except Exception:
                pass
    finally:
        db_outer.close()

    db = SessionLocal()
    written = 0
    try:
        for entry in rows:
            cid = entry.get("id")
            if not cid:
                continue
            career = entry.get("career") or []
            existing = db.get(CoachProfile, cid)
            row = existing or CoachProfile(api_coach_id=cid)
            row.name = entry.get("name")
            row.firstname = entry.get("firstname")
            row.lastname = entry.get("lastname")
            row.age = _to_int(entry.get("age"))
            row.birth_date = entry.get("birth", {}).get("date") if isinstance(entry.get("birth"), dict) else None
            row.birth_place = entry.get("birth", {}).get("place") if isinstance(entry.get("birth"), dict) else None
            row.birth_country = entry.get("birth", {}).get("country") if isinstance(entry.get("birth"), dict) else None
            row.nationality = entry.get("nationality")
            row.height = entry.get("height")
            row.weight = entry.get("weight")
            row.photo_url = entry.get("photo")
            row.team_api_id = team_id
            row.team_name = entry.get("team", {}).get("name") if isinstance(entry.get("team"), dict) else None
            row.career_json = json.dumps(career) if career else None
            if not existing:
                db.add(row)
            written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_coaches", str(exc))
    finally:
        db.close()
    return written


def _normalise_transfers(raw: HarvestRaw) -> int:
    """Normalise /transfers (player- or team-scoped) into PlayerTransfer rows.

    Accepts both /transfers?player=X (single player) and /transfers?team=X
    (every player who moved through that team). Player identity is read from
    each response entry's body, falling back to the job's player param.
    """
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    pid = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                pid = (json.loads(job.params_json) or {}).get("player")
            except Exception:
                pass
    finally:
        db_outer.close()

    db = SessionLocal()
    written = 0
    try:
        for entry in rows:
            transfers_list = entry.get("transfers") or []
            entry_player = entry.get("player") if isinstance(entry.get("player"), dict) else {}
            # Prefer the per-entry player id from the response body — this lets a
            # team-scoped /transfers?team=X response (many players) attribute each
            # transfer to the right player. Fall back to the job's player param
            # for the legacy /transfers?player=X single-player shape.
            entry_pid = entry_player.get("id") or pid
            player_name = entry_player.get("name")
            for tr in transfers_list:
                tdate_str = tr.get("date")
                tdate = None
                if tdate_str:
                    try:
                        tdate = datetime.fromisoformat(str(tdate_str)[:10])
                    except Exception:
                        pass
                db.add(PlayerTransfer(
                    player_api_id=entry_pid or 0,
                    player_name=player_name,
                    transfer_date=tdate,
                    from_team_id=(tr.get("teams", {}).get("out", {}) or {}).get("id") if isinstance(tr.get("teams"), dict) else None,
                    from_team_name=(tr.get("teams", {}).get("out", {}) or {}).get("name") if isinstance(tr.get("teams"), dict) else None,
                    to_team_id=(tr.get("teams", {}).get("in", {}) or {}).get("id") if isinstance(tr.get("teams"), dict) else None,
                    to_team_name=(tr.get("teams", {}).get("in", {}) or {}).get("name") if isinstance(tr.get("teams"), dict) else None,
                    transfer_type=tr.get("type"),
                ))
                written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_transfers", str(exc))
    finally:
        db.close()
    return written


def _normalise_sidelined(raw: HarvestRaw) -> int:
    """Normalise /sidelined?team=X into PlayerSidelined rows."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    team_id = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                team_id = (json.loads(job.params_json) or {}).get("team")
            except Exception:
                pass
    finally:
        db_outer.close()

    db = SessionLocal()
    written = 0
    try:
        for entry in rows:
            player = entry.get("player") or {}
            pid = player.get("id")
            pname = player.get("name")
            for item in entry.get("sidelined") or entry if isinstance(entry, dict) else []:
                if not isinstance(item, dict):
                    continue
                stype = item.get("type")
                reason = item.get("reason") or item.get("description")
                start_str = item.get("start") or item.get("start_date")
                end_str = item.get("end") or item.get("end_date")
                start_date = datetime.fromisoformat(str(start_str)[:10]) if start_str else None
                end_date = datetime.fromisoformat(str(end_str)[:10]) if end_str else None
                db.add(PlayerSidelined(
                    player_api_id=pid or 0,
                    player_name=pname,
                    team_api_id=team_id,
                    team_name=entry.get("team", {}).get("name") if isinstance(entry.get("team"), dict) else None,
                    type=stype,
                    reason=reason,
                    start_date=start_date,
                    end_date=end_date,
                ))
                written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_sidelined", str(exc))
    finally:
        db.close()
    return written


def _normalise_team_stats(raw: HarvestRaw) -> int:
    """Normalise /teams/statistics into TeamSeasonProfile rows.

    Response includes per-minute-band goals/cards, formations, home/away splits."""
    try:
        data = json.loads(raw.response_json)
        resp = data.get("response", {}) or {}
    except Exception:
        return 0

    team = resp.get("team") or {}
    tid = team.get("id")
    if not tid:
        return 0

    league_data = resp.get("league") or {}
    league_id = league_data.get("id")
    season = league_data.get("season")

    if not league_id or not season:
        return 0

    db = SessionLocal()
    written = 0
    try:
        # Fixtures breakdown
        fixtures = resp.get("fixtures") or {}
        played = fixtures.get("played") or {}
        wins = fixtures.get("wins") or {}
        draws = fixtures.get("draws") or {}
        loses = fixtures.get("loses") or {}

        # Goals
        goals = resp.get("goals") or {}
        goals_for = goals.get("for") or {}
        goals_against = goals.get("against") or {}

        # Cards
        cards = resp.get("cards") or {}
        yellows = cards.get("yellow") or {}
        reds = cards.get("red") or {}

        # Other
        clean_sheets = resp.get("clean_sheet") or {}
        failed_to_score = resp.get("failed_to_score") or {}
        penalties = resp.get("penalty") or {}

        # Formations
        formations = resp.get("formations") or resp.get("lineups") or []
        if isinstance(formations, list):
            formations_json = json.dumps([
                {"formation": f.get("formation"), "played": f.get("played")}
                for f in formations if isinstance(f, dict)
            ]) if formations else None
        else:
            formations_json = None

        # Biggest results
        biggest = resp.get("biggest") or {}
        biggest_wins = biggest.get("wins") or {}
        biggest_losses = biggest.get("loses") or {}

        existing = (
            db.query(TeamSeasonProfile)
            .filter(TeamSeasonProfile.team_api_id == tid)
            .filter(TeamSeasonProfile.league_id == league_id)
            .filter(TeamSeasonProfile.season == season)
            .first()
        )
        row = existing or TeamSeasonProfile(
            team_api_id=tid, league_id=league_id, season=season,
        )
        row.team_name = team.get("name")
        row.league_name = league_data.get("name")
        row.matches_played_total = played.get("total") or 0
        row.matches_played_home = played.get("home") or 0
        row.matches_played_away = played.get("away") or 0
        row.wins_home = wins.get("home") or 0
        row.wins_away = wins.get("away") or 0
        row.draws_home = draws.get("home") or 0
        row.draws_away = draws.get("away") or 0
        row.loses_home = loses.get("home") or 0
        row.loses_away = loses.get("away") or 0
        row.goals_for_total = goals_for.get("total", {}).get("total") if isinstance(goals_for.get("total"), dict) else (goals_for.get("total") or 0)
        row.goals_for_avg = _to_float(goals_for.get("average", {}).get("total") if isinstance(goals_for.get("average"), dict) else goals_for.get("average"))
        row.goals_against_total = goals_against.get("total", {}).get("total") if isinstance(goals_against.get("total"), dict) else (goals_against.get("total") or 0)
        row.goals_against_avg = _to_float(goals_against.get("average", {}).get("total") if isinstance(goals_against.get("average"), dict) else goals_against.get("average"))
        row.clean_sheets_total = clean_sheets.get("total") or 0
        row.failed_to_score_total = failed_to_score.get("total") or 0
        row.avg_possession = _to_float(resp.get("possession", {}).get("average") if isinstance(resp.get("possession"), dict) else None)
        row.yellow_cards_per_game = _to_float(cards.get("yellow", {}).get("average", {}).get("total") if isinstance(cards.get("yellow"), dict) and isinstance(cards.get("yellow", {}).get("average"), dict) else None) or _to_float(cards.get("yellow", [{}])[0].get("average") if isinstance(cards.get("yellow"), list) else None)
        row.red_cards_per_game = _to_float(cards.get("red", {}).get("average", {}).get("total") if isinstance(cards.get("red"), dict) and isinstance(cards.get("red", {}).get("average"), dict) else None) or _to_float(cards.get("red", [{}])[0].get("average") if isinstance(cards.get("red"), list) else None)
        row.penalties_scored_pct = _to_float(penalties.get("scored", {}).get("percentage") if isinstance(penalties.get("scored"), dict) else penalties.get("scored"))
        row.formations_json = formations_json
        row.goals_for_minute_json = json.dumps(goals_for.get("minute")) if goals_for.get("minute") else None
        row.goals_against_minute_json = json.dumps(goals_against.get("minute")) if goals_against.get("minute") else None
        row.cards_yellow_minute_json = json.dumps(yellows) if yellows else None
        row.cards_red_minute_json = json.dumps(reds) if reds else None
        row.biggest_win_home = biggest_wins.get("home") or biggest.get("streak", {}).get("wins") if isinstance(biggest.get("streak"), dict) else None
        row.biggest_win_away = biggest_wins.get("away")
        row.biggest_loss_home = biggest_losses.get("home")
        row.biggest_loss_away = biggest_losses.get("away")
        if not existing:
            db.add(row)
        written = 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_team_stats", str(exc))
    finally:
        db.close()
    return written


def _normalise_topscorers(raw: HarvestRaw) -> int:
    """Normalise /players/topscorers?league=X&season=Y into PlayerSeasonStats.
    Each entry has player + statistics[0] with goals/assists/shots/etc."""
    try:
        data = json.loads(raw.response_json)
        entries = data.get("response", []) or []
    except Exception:
        return 0

    league_id = season = None
    db_outer = SessionLocal()
    try:
        job = db_outer.query(HarvestJob).filter(HarvestJob.id == raw.job_id).first()
        if job and job.params_json:
            try:
                p = json.loads(job.params_json) or {}
                league_id = p.get("league")
                season = p.get("season")
            except Exception:
                pass
    finally:
        db_outer.close()

    if not league_id or not season:
        return 0

    db = SessionLocal()
    written = 0
    try:
        for entry in entries:
            player = entry.get("player") or {}
            pid = player.get("id")
            if not pid:
                continue
            stats_list = entry.get("statistics") or []
            if not stats_list:
                continue
            s = stats_list[0]
            team = s.get("team") or {}

            games = s.get("games") or {}
            goals = s.get("goals") or {}
            shots = s.get("shots") or {}
            passes = s.get("passes") or {}
            tackles = s.get("tackles") or {}
            dribbles = s.get("dribbles") or {}
            duels = s.get("duels") or {}
            cards = s.get("cards") or {}
            penalty = s.get("penalty") or {}

            existing = (
                db.query(PlayerSeasonStats)
                .filter(PlayerSeasonStats.player_api_id == pid)
                .filter(PlayerSeasonStats.team_api_id == team.get("id"))
                .filter(PlayerSeasonStats.league_id == league_id)
                .filter(PlayerSeasonStats.season == season)
                .first()
            )
            row = existing or PlayerSeasonStats(
                player_api_id=pid, team_api_id=team.get("id") or 0,
                league_id=league_id, season=season,
            )
            row.league_name = s.get("league", {}).get("name") if isinstance(s.get("league"), dict) else None
            row.appearances = games.get("appearences") or games.get("appearances") or 0
            row.minutes = games.get("minutes") or 0
            row.position = games.get("position")
            row.rating = _to_float(games.get("rating"))
            row.goals_total = goals.get("total") or 0
            row.assists_total = goals.get("assists") or 0
            row.shots_total = shots.get("total") or 0
            row.shots_on = shots.get("on") or 0
            row.passes_total = passes.get("total") or 0
            row.passes_accuracy = _to_int(passes.get("accuracy"))
            row.tackles_total = tackles.get("total") or 0
            row.dribbles_attempts = dribbles.get("attempts") or 0
            row.duels_won = duels.get("won") or 0
            row.yellow_cards = cards.get("yellow") or 0
            row.red_cards = cards.get("red") or 0
            row.penalty_scored = penalty.get("scored") or 0
            row.penalty_missed = penalty.get("missed") or 0
            row.penalty_won = penalty.get("won") or 0
            if not existing:
                db.add(row)
            written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_topscorers", str(exc))
    finally:
        db.close()
    return written


def _normalise_h2h(raw: HarvestRaw) -> int:
    """Normalise /fixtures/h2h into MatchH2H rows (idempotent append).
    Each entry is a past meeting between two teams."""
    try:
        data = json.loads(raw.response_json)
        rows = data.get("response", []) or []
    except Exception:
        return 0

    from backend.db.models import MatchH2H

    db = SessionLocal()
    written = 0
    try:
        for entry in rows:
            fixture = entry.get("fixture") or {}
            fid = fixture.get("id")
            if not fid:
                continue
            teams = entry.get("teams") or {}
            home = teams.get("home") or {}
            away = teams.get("away") or {}
            goals = entry.get("goals") or {}
            league = entry.get("league") or {}

            home_id = home.get("id")
            away_id = away.get("id")
            if not home_id or not away_id:
                continue

            existing = db.query(MatchH2H).filter(
                MatchH2H.api_fixture_id == fid
            ).first()
            if existing:
                continue

            fdate = None
            try:
                d = fixture.get("date")
                if d:
                    fdate = datetime.fromisoformat(str(d)[:10])
            except Exception:
                pass

            db.add(MatchH2H(
                api_fixture_id=fid,
                team1_id=min(home_id, away_id),
                team2_id=max(home_id, away_id),
                home_team_id=home_id,
                home_team_name=home.get("name"),
                away_team_id=away_id,
                away_team_name=away.get("name"),
                home_score=goals.get("home"),
                away_score=goals.get("away"),
                fixture_date=fdate,
                league_name=league.get("name"),
                venue=fixture.get("venue", {}).get("name") if isinstance(fixture.get("venue"), dict) else None,
            ))
            written += 1
        db.commit()
    except Exception as exc:
        _log_error(raw.job_id, raw.endpoint, "normalise_h2h", str(exc))
    finally:
        db.close()
    return written


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
    "/players/topscorers":  _normalise_topscorers,
    "/players/topassists":  _normalise_topscorers,  # same shape as topscorers
    "/fixtures/statistics": _normalise_statistics,
    "/fixtures/events":     _normalise_events,
    "/fixtures/players":    _normalise_fixture_players,
    "/fixtures/lineups":    _normalise_lineups,
    "/fixtures/h2h":        _normalise_h2h,
    "/fixtures":            _normalise_fixtures,
    "/predictions":         _normalise_prediction,
    "/odds":                _normalise_odds,
    "/standings":           _normalise_standings,
    "/teams/statistics":    _normalise_team_stats,
    "/coachs":              _normalise_coaches,
    "/transfers":           _normalise_transfers,
    "/sidelined":           _normalise_sidelined,
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
