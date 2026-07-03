"""Idempotent writers for the persistent api-football archive.

Every signal we pull from api-football lands in one of the tables defined in
backend/db/models.py (MatchEvent, MatchLineup, MatchStatistics, ApiFootballPrediction,
MatchH2H, PlayerProfile, PlayerTournamentStats, TeamSeasonStats). Each writer is safe
to call repeatedly with the same payload — duplicates are detected on a natural key,
not the autoincrement id — so the live poller can call them every 30s during play
without bloating the DB.

After a match reaches FT, the data here is the source of truth and the API is never
hit again for that match's events/stats/lineups/predictions.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import (
    ApiFootballPrediction,
    MatchEvent,
    MatchH2H,
    MatchLineup,
    MatchLineupPlayer,
    MatchStatistics,
    PlayerProfile,
    PlayerTournamentStats,
    TeamSeasonStats,
)


# -----------------------------------------------------------------------------
# Events: goals, cards, subs, VAR. Called from live poller every 30s.
# -----------------------------------------------------------------------------

def is_shootout_event(elapsed: int | None, extra: int | None, comments: str | None) -> bool:
    """True when an event belongs to a penalty shootout rather than open play.

    api-football stamps shootout kicks with comments="Penalty Shootout" and
    elapsed=120; older payloads omit the comment and only mark them by a
    minute past 120. Shared by score_sanity, push_dispatch and the storylines
    scorer tally so none of them count shootout kicks as match goals.
    """
    if (comments or "").lower().find("shootout") >= 0:
        return True
    return ((elapsed or 0) + (extra or 0)) > 120


def persist_events(db: Session, match_id: str, api_fixture_id: int, raw_events: list[dict],
                   reconcile: bool = False) -> int:
    """Insert any new events for this match. Idempotency key:
    (match_id, type, DETAIL, elapsed, extra, player_id, team_id). Returns count
    inserted. `detail` is in the key because a shootout makes (type="Goal",
    elapsed=120, same player) legitimately recur — e.g. a sudden-death second
    kick, or a scored reg pen at 120' plus a shootout kick. Without detail the
    second event silently collided and was dropped.

    reconcile=True additionally treats `raw_events` as the CURRENT complete
    event list for the fixture: archived rows missing from it get
    superseded_at stamped (api-football revises events after first emission —
    scorer re-attributions, own-goal corrections, minute shifts — and the
    insert-only archive was keeping every revision as a phantom extra event;
    M088's 1-1 recap showed 3 goal rows). Rows that reappear in a later
    payload are un-superseded, so a transiently partial API response
    self-heals on the next pass. Only pass reconcile=True with a payload
    fetched fresh from the API (live poller, archive backfill) — NEVER from a
    stored harvest blob, which may be older than the rows it would supersede.
    """
    if not raw_events:
        return 0

    def _row_key(r: MatchEvent) -> tuple:
        return (r.type, r.detail, r.elapsed, r.extra, r.player_id, r.team_id)

    # Full ORM rows (not just key tuples): reconcile needs superseded_at
    # access, and per-match event counts are tiny (< ~120 rows).
    rows = db.query(MatchEvent).filter(MatchEvent.match_id == match_id).all()
    seen = {_row_key(r) for r in rows}

    inserted = 0
    payload_keys: set[tuple] = set()
    for e in raw_events:
        time = e.get("time") or {}
        player = e.get("player") or {}
        assist = e.get("assist") or {}
        team = e.get("team") or {}
        key = (
            e.get("type"),
            e.get("detail"),
            time.get("elapsed"),
            time.get("extra"),
            player.get("id"),
            team.get("id"),
        )
        payload_keys.add(key)
        if key in seen:
            continue
        seen.add(key)
        db.add(MatchEvent(
            match_id=match_id,
            api_fixture_id=api_fixture_id,
            elapsed=time.get("elapsed"),
            extra=time.get("extra"),
            type=e.get("type"),
            detail=e.get("detail"),
            player_id=player.get("id"),
            player_name=player.get("name"),
            assist_id=assist.get("id"),
            assist_name=assist.get("name"),
            team_id=team.get("id"),
            team_name=team.get("name"),
            comments=e.get("comments"),
        ))
        inserted += 1

    if reconcile:
        now = datetime.utcnow()
        for r in rows:
            k = _row_key(r)
            if k not in payload_keys and r.superseded_at is None:
                r.superseded_at = now
            elif k in payload_keys and r.superseded_at is not None:
                r.superseded_at = None
    return inserted


# -----------------------------------------------------------------------------
# Statistics: per-team. Updated during play, locked once is_final=True.
# -----------------------------------------------------------------------------

def _stat_to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except Exception:
        return None


def _stat_to_pct(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        if isinstance(v, str) and v.endswith("%"):
            return float(v.rstrip("%"))
        return float(v)
    except Exception:
        return None


def _stat_to_float(v) -> Optional[float]:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except Exception:
        return None


def _map_team_stats(stats_dict: dict) -> dict:
    """Map api-football's flat statistics dict (type:value) to MatchStatistics columns."""
    return {
        "shots_on_goal": _stat_to_int(stats_dict.get("Shots on Goal")),
        "shots_off_goal": _stat_to_int(stats_dict.get("Shots off Goal")),
        "total_shots": _stat_to_int(stats_dict.get("Total Shots")),
        "blocked_shots": _stat_to_int(stats_dict.get("Blocked Shots")),
        "shots_inside_box": _stat_to_int(stats_dict.get("Shots insidebox")),
        "shots_outside_box": _stat_to_int(stats_dict.get("Shots outsidebox")),
        "fouls": _stat_to_int(stats_dict.get("Fouls")),
        "corner_kicks": _stat_to_int(stats_dict.get("Corner Kicks")),
        "offsides": _stat_to_int(stats_dict.get("Offsides")),
        "ball_possession": _stat_to_pct(stats_dict.get("Ball Possession")),
        "yellow_cards": _stat_to_int(stats_dict.get("Yellow Cards")),
        "red_cards": _stat_to_int(stats_dict.get("Red Cards")),
        "goalkeeper_saves": _stat_to_int(stats_dict.get("Goalkeeper Saves")),
        "total_passes": _stat_to_int(stats_dict.get("Total passes")),
        "passes_accurate": _stat_to_int(stats_dict.get("Passes accurate")),
        "passes_pct": _stat_to_pct(stats_dict.get("Passes %")),
        "expected_goals": _stat_to_float(stats_dict.get("expected_goals")),
    }


def persist_statistics(
    db: Session,
    match_id: str,
    api_fixture_id: int,
    raw_stats_response: list[dict],
    is_final: bool = False,
) -> int:
    """Upsert team stats. raw_stats_response is the full /fixtures/statistics list.
    Returns count written/updated. If a row already has is_final=True we never overwrite."""
    if not raw_stats_response:
        return 0
    written = 0
    for team_block in raw_stats_response:
        team = team_block.get("team") or {}
        team_id = team.get("id")
        if not team_id:
            continue
        stats_flat = {s.get("type"): s.get("value") for s in (team_block.get("statistics") or [])}
        mapped = _map_team_stats(stats_flat)

        existing = (
            db.query(MatchStatistics)
            .filter(MatchStatistics.match_id == match_id, MatchStatistics.team_id == team_id)
            .first()
        )
        if existing and existing.is_final:
            continue  # locked
        if existing:
            for k, v in mapped.items():
                setattr(existing, k, v)
            existing.is_final = is_final
            existing.captured_at = datetime.utcnow()
        else:
            db.add(MatchStatistics(
                match_id=match_id,
                api_fixture_id=api_fixture_id,
                team_id=team_id,
                team_name=team.get("name"),
                is_final=is_final,
                **mapped,
            ))
        written += 1
    return written


# -----------------------------------------------------------------------------
# Lineups: starting XI + bench, with formation. Captured once.
# -----------------------------------------------------------------------------

def persist_lineups(
    db: Session,
    match_id: str,
    api_fixture_id: int,
    raw_lineups: list[dict],
) -> int:
    """Insert lineups once per (match_id, team_id). Subsequent calls no-op."""
    if not raw_lineups:
        return 0
    inserted = 0
    for block in raw_lineups:
        team = block.get("team") or {}
        team_id = team.get("id")
        if not team_id:
            continue
        existing = (
            db.query(MatchLineup)
            .filter(MatchLineup.match_id == match_id, MatchLineup.team_id == team_id)
            .first()
        )
        if existing:
            continue

        coach = block.get("coach") or {}
        lineup = MatchLineup(
            match_id=match_id,
            api_fixture_id=api_fixture_id,
            team_id=team_id,
            team_name=team.get("name"),
            formation=block.get("formation"),
            coach_id=coach.get("id"),
            coach_name=coach.get("name"),
        )
        db.add(lineup)
        db.flush()  # need lineup.id for the FK

        for p in (block.get("startXI") or []):
            pl = p.get("player") or {}
            db.add(MatchLineupPlayer(
                lineup_id=lineup.id,
                match_id=match_id,
                player_id=pl.get("id"),
                player_name=pl.get("name"),
                number=pl.get("number"),
                position=pl.get("pos"),
                grid=pl.get("grid"),
                is_starter=True,
            ))
        for p in (block.get("substitutes") or []):
            pl = p.get("player") or {}
            db.add(MatchLineupPlayer(
                lineup_id=lineup.id,
                match_id=match_id,
                player_id=pl.get("id"),
                player_name=pl.get("name"),
                number=pl.get("number"),
                position=pl.get("pos"),
                grid=pl.get("grid"),
                is_starter=False,
            ))
        inserted += 1
    return inserted


# -----------------------------------------------------------------------------
# api-football prediction: captured ONCE per match.
# -----------------------------------------------------------------------------

def persist_api_prediction(
    db: Session,
    match_id: str,
    api_fixture_id: int,
    raw: dict,
) -> bool:
    """Upsert the pre-match prediction snapshot. Returns True if written."""
    if not raw:
        return False
    existing = (
        db.query(ApiFootballPrediction)
        .filter(ApiFootballPrediction.match_id == match_id)
        .first()
    )
    if existing:
        return False  # already captured

    pred = raw.get("predictions") or {}
    comp = raw.get("comparison") or {}
    goals = pred.get("goals") or {}
    pct = pred.get("percent") or {}
    winner = pred.get("winner") or {}

    def s(d, k):
        return (d or {}).get(k)

    db.add(ApiFootballPrediction(
        match_id=match_id,
        api_fixture_id=api_fixture_id,
        winner_id=winner.get("id"),
        winner_name=winner.get("name"),
        winner_comment=winner.get("comment"),
        win_or_draw=pred.get("win_or_draw"),
        under_over=pred.get("under_over"),
        goals_home=_stat_to_float(goals.get("home")),
        goals_away=_stat_to_float(goals.get("away")),
        advice=pred.get("advice"),
        pct_home=pct.get("home"),
        pct_draw=pct.get("draw"),
        pct_away=pct.get("away"),
        comp_form_home=s(comp.get("form"), "home"),
        comp_form_away=s(comp.get("form"), "away"),
        comp_att_home=s(comp.get("att"), "home"),
        comp_att_away=s(comp.get("att"), "away"),
        comp_def_home=s(comp.get("def"), "home"),
        comp_def_away=s(comp.get("def"), "away"),
        comp_poisson_home=s(comp.get("poisson_distribution"), "home"),
        comp_poisson_away=s(comp.get("poisson_distribution"), "away"),
        comp_h2h_home=s(comp.get("h2h"), "home"),
        comp_h2h_away=s(comp.get("h2h"), "away"),
        comp_goals_home=s(comp.get("goals"), "home"),
        comp_goals_away=s(comp.get("goals"), "away"),
        comp_total_home=s(comp.get("total"), "home"),
        comp_total_away=s(comp.get("total"), "away"),
    ))
    return True


# -----------------------------------------------------------------------------
# H2H: archived forever, keyed on canonical (team1_id < team2_id).
# -----------------------------------------------------------------------------

def persist_h2h(db: Session, raw_fixtures: list[dict]) -> int:
    """Insert any new H2H fixtures we have not seen before. raw_fixtures is the
    /fixtures/headtohead response list."""
    if not raw_fixtures:
        return 0
    inserted = 0
    for fx in raw_fixtures:
        fixture = fx.get("fixture") or {}
        api_fixture_id = fixture.get("id")
        if not api_fixture_id:
            continue
        existing = (
            db.query(MatchH2H)
            .filter(MatchH2H.api_fixture_id == api_fixture_id)
            .first()
        )
        if existing:
            continue
        teams = fx.get("teams") or {}
        home = teams.get("home") or {}
        away = teams.get("away") or {}
        league = fx.get("league") or {}
        goals = fx.get("goals") or {}
        hid = home.get("id")
        aid = away.get("id")
        if not hid or not aid:
            continue

        # Canonical key: smaller id first so lookup is order-agnostic
        t1, t2 = (hid, aid) if hid < aid else (aid, hid)
        date_str = fixture.get("date")
        try:
            fdate = datetime.fromisoformat(date_str.replace("Z", "+00:00")) if date_str else None
        except Exception:
            fdate = None

        db.add(MatchH2H(
            api_fixture_id=api_fixture_id,
            team1_id=t1,
            team2_id=t2,
            fixture_date=fdate,
            league_id=league.get("id"),
            league_name=league.get("name"),
            season=league.get("season"),
            home_team_id=hid,
            home_team_name=home.get("name"),
            away_team_id=aid,
            away_team_name=away.get("name"),
            home_score=goals.get("home"),
            away_score=goals.get("away"),
            status_short=(fixture.get("status") or {}).get("short"),
        ))
        inserted += 1
    return inserted


# -----------------------------------------------------------------------------
# Player profiles: upserted by player_id.
# -----------------------------------------------------------------------------

def persist_player_profile(db: Session, raw: dict, team_id: int | None = None,
                            team_name: str | None = None, position: str | None = None) -> bool:
    """Upsert one PlayerProfile by api-football player_id."""
    player_id = raw.get("id")
    if not player_id:
        return False
    birth = raw.get("birth") or {}
    existing = db.query(PlayerProfile).filter(PlayerProfile.player_id == player_id).first()
    if existing:
        # Refresh basic info if changed
        existing.name = raw.get("name") or existing.name
        existing.age = raw.get("age") or existing.age
        existing.photo_url = raw.get("photo") or existing.photo_url
        if team_id: existing.team_id = team_id
        if team_name: existing.team_name = team_name
        if position: existing.position = position
        existing.updated_at = datetime.utcnow()
        return False
    db.add(PlayerProfile(
        player_id=player_id,
        name=raw.get("name"),
        firstname=raw.get("firstname"),
        lastname=raw.get("lastname"),
        age=raw.get("age"),
        birth_date=birth.get("date"),
        birth_place=birth.get("place"),
        birth_country=birth.get("country"),
        nationality=raw.get("nationality"),
        height=raw.get("height"),
        weight=raw.get("weight"),
        photo_url=raw.get("photo"),
        team_id=team_id,
        team_name=team_name,
        position=position,
    ))
    return True


# -----------------------------------------------------------------------------
# Aggregations: rebuilt after each FT from the persistent tables.
# Zero API cost.
# -----------------------------------------------------------------------------

def disallowed_goal_keys(db: Session) -> set:
    """Return the set of (match_id, elapsed, player_id) tuples for goals that
    were VAR-disallowed. Lets any consumer that aggregates goal events
    (player stats, scorer lines on the live feed, recap timelines) exclude
    or annotate them. api-football marks the disallowed goal with the
    original 'Goal' event AND a follow-up 'Var' event at the same minute
    with detail like 'Goal Disallowed - Foul' or 'Goal cancelled'.

    Without this filter, Vinicius Junior's VAR'd goal vs Scotland on
    2026-06-24 was being credited to his tournament tally."""
    from sqlalchemy import or_
    var_events = db.query(MatchEvent).filter(
        MatchEvent.superseded_at.is_(None),
        MatchEvent.type == "Var",
        or_(
            MatchEvent.detail.ilike("%disallowed%"),
            MatchEvent.detail.ilike("%cancelled%"),
            MatchEvent.detail.ilike("%canceled%"),
        ),
    ).all()
    out: set[tuple[str, int, int]] = set()
    for v in var_events:
        if v.player_id and v.elapsed is not None:
            out.add((v.match_id, v.elapsed, v.player_id))
    return out


def duplicate_goal_ids(db: Session, window_minutes: int = 3) -> set[int]:
    """IDs of MatchEvent rows that are duplicate-goal emissions from
    api-football. The provider often re-emits the same goal with a
    slightly adjusted minute (e.g. 45+3' becomes 48' in the reconciled
    stats run, or 11' becomes 10' after their internal clock sync).
    Same player_id, same match, same Goal type, elapsed within 3 mins.

    Returns the set of event IDs that should be IGNORED in any tally.
    The earlier-captured event wins because the live tick is closer to
    real-time truth; the later reconciliation is what's wrong.

    Without this filter, Vinicius Junior was credited with 4 tournament
    goals (3 real + 1 duplicate re-emission from M031) even after the
    VAR filter; the user expected 3 (the official count)."""
    rows = (
        db.query(MatchEvent)
        .filter(MatchEvent.type == "Goal")
        .filter(MatchEvent.detail.notin_(["Own Goal", "Missed Penalty"]))
        .filter(MatchEvent.player_id.isnot(None))
        .filter(MatchEvent.superseded_at.is_(None))
        .order_by(MatchEvent.match_id, MatchEvent.player_id, MatchEvent.captured_at)
        .all()
    )
    # Group by (match_id, player_id) and within each group flag any event
    # whose absolute-minute (elapsed + extra) is within window_minutes of
    # an earlier-captured one in the same group.
    dup_ids: set[int] = set()
    by_key: dict[tuple, list] = {}
    for r in rows:
        key = (r.match_id, r.player_id)
        by_key.setdefault(key, []).append(r)
    for key, evs in by_key.items():
        if len(evs) < 2:
            continue
        # Sort by captured_at ascending so kept[0] is the FIRST captured.
        evs.sort(key=lambda e: e.captured_at or datetime.utcnow())
        kept_minutes: list[int] = []
        for e in evs:
            mins = (e.elapsed or 0) + (e.extra or 0)
            if any(abs(mins - km) <= window_minutes for km in kept_minutes):
                dup_ids.add(e.id)
            else:
                kept_minutes.append(mins)
    return dup_ids


def rebuild_player_tournament_stats(db: Session, tournament: str = "WC2026") -> int:
    """Recompute per-player goals/assists/cards from MatchEvent. Pure SQL aggregation,
    no API. Wipes and rewrites all WC2026 rows."""
    # Wipe
    db.query(PlayerTournamentStats).filter(
        PlayerTournamentStats.tournament == tournament
    ).delete()
    db.flush()

    # Aggregate from events
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.player_id.isnot(None))
        .filter(MatchEvent.superseded_at.is_(None))
        .all()
    )
    # Goals that VAR ruled out shouldn't count toward player tallies.
    var_disallowed = disallowed_goal_keys(db)
    # api-football re-emits some goals at adjusted minutes during their stat
    # reconciliation. Filter those duplicates out.
    dup_ids = duplicate_goal_ids(db)

    def _blank_row(pid, name, team_id, team_name):
        return {
            "player_id": pid,
            "player_name": name,
            "team_id": team_id,
            "team_name": team_name,
            "goals": 0, "assists": 0, "yellow_cards": 0, "red_cards": 0,
            "own_goals": 0, "penalty_goals": 0,
            # Spot-kick book-keeping. attempts = scored + missed. Shootout
            # rows kept apart so a regulation pen-miss doesn't pollute the
            # shootout-skill signal we use for pen-shootout pricing.
            "penalty_attempts": 0, "penalty_misses": 0,
            "shootout_penalty_goals": 0, "shootout_penalty_misses": 0,
        }

    agg: dict[int, dict] = {}
    for e in events:
        pid = e.player_id
        if pid not in agg:
            agg[pid] = _blank_row(pid, e.player_name, e.team_id, e.team_name)
        row = agg[pid]
        # Maintain latest seen name/team
        if e.player_name:
            row["player_name"] = e.player_name
        if e.team_id:
            row["team_id"] = e.team_id
            row["team_name"] = e.team_name

        if e.type == "Goal":
            # VAR'd goals do not count. Vinicius vs Scotland, 2026-06-24
            # exposed this gap: his disallowed strike was inflating his
            # tournament total to 4 instead of 3.
            if (e.match_id, e.elapsed, pid) in var_disallowed:
                continue
            # Duplicate goal re-emissions from api-football (see
            # duplicate_goal_ids). Same player, same match, same goal,
            # different reported minute.
            if e.id in dup_ids:
                continue
            # api-football marks shootout kicks with comments="Penalty Shootout".
            # Some older payloads omit the comment and only mark them by an
            # elapsed minute >120 (i.e. after extra-time has finished). Treat
            # both as shootout context so we never miss-attribute one.
            is_shootout = (
                (e.comments or "").lower().find("shootout") >= 0
                or (e.elapsed or 0) > 120
            )
            if e.detail == "Own Goal":
                row["own_goals"] += 1
            elif e.detail == "Missed Penalty":
                # CRITICAL: was previously falling through to the goals++
                # branch — meaning Messi's miss showed up as a goal in the
                # tournament leaderboard. Now counted as an attempt but NOT
                # a goal, and split into regulation vs shootout buckets.
                row["penalty_attempts"] += 1
                row["penalty_misses"] += 1
                if is_shootout:
                    row["shootout_penalty_misses"] += 1
            elif e.detail == "Penalty":
                row["penalty_attempts"] += 1
                row["penalty_goals"] += 1
                row["goals"] += 1
                if is_shootout:
                    row["shootout_penalty_goals"] += 1
            else:
                # Normal Goal — open play.
                row["goals"] += 1
        elif e.type == "Card":
            if e.detail == "Yellow Card":
                row["yellow_cards"] += 1
            elif e.detail in ("Red Card", "Second Yellow card"):
                row["red_cards"] += 1

    # Add assists separately (they have a different player_id field).
    # Missed penalties never have an assist field, so the goal-detail
    # filter below isn't strictly needed today, but we keep it explicit
    # so a future event-type tweak can't silently inflate assist counts.
    # Also skip assists on VAR-disallowed goals (the goal didn't happen,
    # so neither did the assist) and on duplicate goal emissions.
    for e in events:
        if (
            e.type == "Goal"
            and e.assist_id
            and e.detail != "Missed Penalty"
            and e.detail != "Own Goal"
            and (e.match_id, e.elapsed, e.player_id) not in var_disallowed
            and e.id not in dup_ids
        ):
            aid = e.assist_id
            if aid not in agg:
                agg[aid] = _blank_row(aid, e.assist_name, e.team_id, e.team_name)
            agg[aid]["assists"] += 1

    for row in agg.values():
        db.add(PlayerTournamentStats(tournament=tournament, **row))
    return len(agg)


def rebuild_team_season_stats(db: Session, tournament: str = "WC2026") -> int:
    """Recompute per-team season totals from MatchStatistics + Match results."""
    from backend.db.models import Match, Team

    db.query(TeamSeasonStats).filter(
        TeamSeasonStats.tournament == tournament
    ).delete()
    db.flush()

    # Index team_id -> Team
    teams = db.query(Team).all()
    matches = db.query(Match).filter(Match.status == "complete").all()
    stats = db.query(MatchStatistics).filter(MatchStatistics.is_final == True).all()

    # Resolve team_id from api-football for our codes via TEAM_IDS map
    from backend.data.fetchers.injuries import TEAM_IDS
    code_by_api = {v: k for k, v in TEAM_IDS.items()}

    agg: dict[str, dict] = {}
    for t in teams:
        agg[t.code] = {
            "team_code": t.code,
            "team_name": t.name,
            "matches_played": 0, "wins": 0, "draws": 0, "losses": 0,
            "goals_for": 0, "goals_against": 0,
            "xg_for": 0.0, "xg_against": 0.0,
            "possession_avg": None,
            "shots_total": 0, "shots_on_target": 0,
            "fouls": 0, "yellow_cards": 0, "red_cards": 0, "clean_sheets": 0,
            "team_id": None,
        }

    # Map match_id -> {home_code, away_code, home_score, away_score}
    by_match = {m.id: m for m in matches}

    # Per-team accumulators for averages
    possession_samples: dict[str, list[float]] = {}

    for s in stats:
        m = by_match.get(s.match_id)
        if not m:
            continue
        team_code = code_by_api.get(s.team_id)
        if not team_code or team_code not in agg:
            continue
        row = agg[team_code]
        row["team_id"] = s.team_id
        if s.shots_on_goal: row["shots_on_target"] += s.shots_on_goal
        if s.total_shots:   row["shots_total"] += s.total_shots
        if s.fouls:         row["fouls"] += s.fouls
        if s.yellow_cards:  row["yellow_cards"] += s.yellow_cards
        if s.red_cards:     row["red_cards"] += s.red_cards
        if s.expected_goals is not None:
            # xG for THIS team, xG against = opp team's xG (we'll resolve in second pass)
            row["xg_for"] += s.expected_goals
        if s.ball_possession is not None:
            possession_samples.setdefault(team_code, []).append(s.ball_possession)

    # xG against and result tallies require pairing the match's two teams
    for m in matches:
        if m.home_score is None or m.away_score is None:
            continue
        h = m.home_code
        a = m.away_code
        if h in agg:
            agg[h]["matches_played"] += 1
            agg[h]["goals_for"] += m.home_score
            agg[h]["goals_against"] += m.away_score
            if m.home_score > m.away_score: agg[h]["wins"] += 1
            elif m.home_score == m.away_score: agg[h]["draws"] += 1
            else: agg[h]["losses"] += 1
            if m.away_score == 0: agg[h]["clean_sheets"] += 1
        if a in agg:
            agg[a]["matches_played"] += 1
            agg[a]["goals_for"] += m.away_score
            agg[a]["goals_against"] += m.home_score
            if m.away_score > m.home_score: agg[a]["wins"] += 1
            elif m.home_score == m.away_score: agg[a]["draws"] += 1
            else: agg[a]["losses"] += 1
            if m.home_score == 0: agg[a]["clean_sheets"] += 1

    # xG against per match (opp's xG_for for that fixture)
    # Build per-match team-xg lookup from MatchStatistics
    match_xg: dict[tuple[str, int], float] = {}
    for s in stats:
        if s.expected_goals is not None:
            match_xg[(s.match_id, s.team_id)] = s.expected_goals
    for m in matches:
        h_id = TEAM_IDS.get(m.home_code)
        a_id = TEAM_IDS.get(m.away_code)
        if not h_id or not a_id: continue
        if m.home_code in agg and (m.id, a_id) in match_xg:
            agg[m.home_code]["xg_against"] += match_xg[(m.id, a_id)]
        if m.away_code in agg and (m.id, h_id) in match_xg:
            agg[m.away_code]["xg_against"] += match_xg[(m.id, h_id)]

    for code, samples in possession_samples.items():
        if samples and code in agg:
            agg[code]["possession_avg"] = sum(samples) / len(samples)

    inserted = 0
    for row in agg.values():
        if row["matches_played"] == 0:
            continue  # skip teams that haven't played yet
        db.add(TeamSeasonStats(tournament=tournament, **row))
        inserted += 1
    return inserted
