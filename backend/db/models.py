from datetime import datetime
from sqlalchemy import Column, String, Float, Integer, DateTime, Boolean, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Team(Base):
    __tablename__ = "teams"
    code = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    fifa_code = Column(String)
    elo = Column(Float, default=1500.0)
    fifa_ranking = Column(Integer)
    primary_color = Column(String, default="#ffffff")
    flag_url = Column(String)
    updated_at = Column(DateTime, default=datetime.utcnow)


class Match(Base):
    __tablename__ = "matches"
    id = Column(String, primary_key=True)
    group = Column(String)
    matchday = Column(Integer)
    kickoff = Column(DateTime)
    venue = Column(String)
    home_code = Column(String)
    away_code = Column(String)
    status = Column(String, default="upcoming")
    home_score = Column(Integer)
    away_score = Column(Integer)
    # Half-time scores — captured from api-football /fixtures `score.halftime`
    # when the harvester sees a FT/AET/PEN status (we already have this data
    # in HarvestRaw blobs, just hadn't normalised it). Nullable so historical
    # matches without an HT recording stay coherent.
    home_ht_score = Column(Integer, nullable=True)
    away_ht_score = Column(Integer, nullable=True)
    # Interruption lifecycle (FRA-IRQ 2026-06-22 weather suspension was
    # ingested as FT 1-0 because we only modelled live vs complete). NULL
    # for the 99% case. Values: 'delayed' (SUSP/INT, may resume same day),
    # 'postponed' (PST, kickoff abandoned), 'abandoned' (ABD/CANC, started
    # but won't finish), 'awarded' (AWD/WO, decided off-pitch). Only NULL
    # and 'awarded' rows are settle-able for picks per industry rules.
    interruption_status = Column(String, nullable=True, index=True)
    interruption_reason = Column(String, nullable=True)
    interruption_started_at = Column(DateTime, nullable=True)
    # Snapshot of the score at the moment play stopped — NOT copied to
    # home_score/away_score unless the match resumes and finishes
    # normally, so calibration and standings stay honest.
    partial_home_score = Column(Integer, nullable=True)
    partial_away_score = Column(Integer, nullable=True)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False)
    market = Column(String, nullable=False)
    our_probability = Column(Float, nullable=False)
    bookmaker_odds = Column(Float)
    ev = Column(Float)
    logged_at = Column(DateTime, default=datetime.utcnow)
    # Closing Line Value: the de-vigged closing line captured near kickoff, and this pick's
    # EV measured against it (clv = p_close_fair * bet_odds - 1). Both nullable — filled in
    # by the CLV job once a match nears kickoff. See backend/data/clv.py.
    closing_odds = Column(Float)
    clv = Column(Float)


class PredictionSnapshot(Base):
    """Full pre-kickoff model distribution for EVERY upcoming match (not just +EV picks),
    so live calibration (RPS/Brier/log-loss) can be scored without the EV-selection bias
    of the Prediction table. Outcome is derived lazily by joining to the completed Match."""
    __tablename__ = "prediction_snapshots"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, unique=True)
    model_version = Column(String)
    p_home = Column(Float)
    p_draw = Column(Float)
    p_away = Column(Float)
    p_over_2_5 = Column(Float)
    p_btts = Column(Float)
    lambda_home = Column(Float)
    lambda_away = Column(Float)
    logged_at = Column(DateTime, default=datetime.utcnow)


class OddsCache(Base):
    __tablename__ = "odds_cache"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False)
    market = Column(String, nullable=False)
    bookmaker = Column(String)
    odds = Column(Float)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class NewsCache(Base):
    __tablename__ = "news_cache"
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_code = Column(String, nullable=False)
    headline = Column(Text)
    source = Column(String)
    url = Column(String)
    published_at = Column(DateTime)
    fetched_at = Column(DateTime, default=datetime.utcnow)


class HistoricalResult(Base):
    __tablename__ = "historical_results"
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime)
    home_team = Column(String)
    away_team = Column(String)
    home_score = Column(Integer)
    away_score = Column(Integer)
    tournament = Column(String)
    neutral = Column(Boolean, default=False)


class PushSubscription(Base):
    """Browser push subscriptions for value-pick alerts."""
    __tablename__ = "push_subscriptions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String, nullable=False, unique=True)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    user_agent = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used = Column(DateTime, default=datetime.utcnow)
    failed_count = Column(Integer, default=0)


class PushSent(Base):
    """Dedup log so the same value pick doesn't notify twice."""
    __tablename__ = "push_sent"
    id = Column(Integer, primary_key=True, autoincrement=True)
    dedup_key = Column(String, nullable=False, unique=True)
    sent_at = Column(DateTime, default=datetime.utcnow)


class LiveMatchState(Base):
    """The current live state of a match — the source of truth that the live-feed
    poller writes and the swing-chart simulator + frontend consume.

    One row per live match. Updated by the poller every 30-60 seconds. The row is kept
    after FT so we can replay the final chart from history.
    """
    __tablename__ = "live_match_state"
    match_id = Column(String, primary_key=True)
    fixture_id_external = Column(Integer)  # api-football fixture id
    status = Column(String)                 # "NS" not started, "1H" first half, "HT" half-time, "2H" second half, "FT" full time, "AET"/"PEN" extra/pens
    elapsed_min = Column(Integer)           # 0..120 (extra time)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    home_red_cards = Column(Integer, default=0)
    away_red_cards = Column(Integer, default=0)
    home_possession = Column(Float)         # percent 0..100, optional
    away_possession = Column(Float)
    home_shots = Column(Integer)
    away_shots = Column(Integer)
    home_shots_on_target = Column(Integer)
    away_shots_on_target = Column(Integer)
    home_xg = Column(Float)                 # accumulated, if feed provides
    away_xg = Column(Float)
    last_event_at = Column(DateTime)        # of most recent feed event we ingested
    updated_at = Column(DateTime, default=datetime.utcnow)


class LiveWpHistory(Base):
    """Per-minute swing-chart points. Bulk-inserted by the simulator after each state
    update. Tail-read by the frontend for the chart, and held forever so post-match
    visitors can replay the full game's WP arc."""
    __tablename__ = "live_wp_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, index=True)
    elapsed_min = Column(Integer, nullable=False)
    p_home = Column(Float, nullable=False)
    p_draw = Column(Float, nullable=False)
    p_away = Column(Float, nullable=False)
    # Optional: per-minute observed metadata (lets the chart annotate "GOAL" markers)
    home_score = Column(Integer)
    away_score = Column(Integer)
    event_label = Column(String)            # "GOAL Mexico (Lainez)" etc, when a tick coincides with an event
    recorded_at = Column(DateTime, default=datetime.utcnow)


class CompetitorPrediction(Base):
    """External forecaster predictions (Opta supercomputer, Bet365 implied, etc.) for
    the public comparison scoreboard. Snapshotted pre-kickoff and never mutated, so the
    Brier-score comparison is honest."""
    __tablename__ = "competitor_predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    forecaster = Column(String, nullable=False)     # "opta", "bet365_implied", "coin_flip"
    match_id = Column(String, nullable=False)
    p_home = Column(Float)
    p_draw = Column(Float)
    p_away = Column(Float)
    source_url = Column(String)                     # original article / odds capture
    snapshotted_at = Column(DateTime, default=datetime.utcnow)


class CompetitorTournamentPrediction(Base):
    """Tournament-level per-team predictions from external forecasters (Opta etc.).
    Used by the public scoreboard's tournament view since per-match 1X2 isn't published
    by every forecaster."""
    __tablename__ = "competitor_tournament_predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    forecaster = Column(String, nullable=False)
    team_code = Column(String, nullable=False)
    team_name = Column(String)
    p_title = Column(Float)        # win the trophy
    p_final = Column(Float)
    p_semi = Column(Float)
    p_quarter = Column(Float)
    p_r16 = Column(Float)
    p_r32 = Column(Float)
    p_first = Column(Float)        # win the group
    p_advance = Column(Float)      # reach round of 32
    source_url = Column(String)
    captured_at = Column(String)   # the date the forecaster published these numbers
    snapshotted_at = Column(DateTime, default=datetime.utcnow)


# =============================================================================
# Persistent api-football archive — write once, read forever.
# These tables are the long-term memory of every signal we pull from api-football.
# Designed so we can rebuild any analytic without re-hitting the API and so we have
# a queryable WC2026 dataset that compounds in value as the tournament progresses.
# =============================================================================


class MatchEvent(Base):
    """Every goal, card, sub, VAR event we have ever seen. Idempotent insert keyed on
    (match_id, type, elapsed, extra, player_id) so the live poller can safely call
    persist_events() every 30s without duplicates."""
    __tablename__ = "match_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, index=True)
    api_fixture_id = Column(Integer, index=True)
    elapsed = Column(Integer)
    extra = Column(Integer)
    type = Column(String)            # Goal, Card, subst, Var
    detail = Column(String)          # Normal Goal, Yellow Card, Red Card, etc
    player_id = Column(Integer, index=True)
    player_name = Column(String)
    assist_id = Column(Integer)
    assist_name = Column(String)
    team_id = Column(Integer, index=True)
    team_name = Column(String)
    comments = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow)


class MatchLineup(Base):
    """Confirmed starting XI + bench. Captured once when api-football publishes it
    (~60 min before kickoff). One row per (match_id, team_id)."""
    __tablename__ = "match_lineups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, index=True)
    api_fixture_id = Column(Integer)
    team_id = Column(Integer, index=True)
    team_name = Column(String)
    formation = Column(String)
    coach_id = Column(Integer)
    coach_name = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow)


class MatchLineupPlayer(Base):
    """One row per player in a confirmed lineup. Used to derive
    PlayerTournamentStats.appearances and minute-tracking."""
    __tablename__ = "match_lineup_players"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lineup_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=False, index=True)
    player_id = Column(Integer, index=True)
    player_name = Column(String)
    number = Column(Integer)
    position = Column(String)       # G, D, M, F
    grid = Column(String)           # "1:1", "4:1" etc
    is_starter = Column(Boolean, default=True)


class MatchStatistics(Base):
    """Final FT stats snapshot per (match_id, team_id). Updated during play and
    locked once status reaches FT (is_final=True). After FT, never re-fetched."""
    __tablename__ = "match_statistics"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, index=True)
    api_fixture_id = Column(Integer)
    team_id = Column(Integer, index=True)
    team_name = Column(String)
    shots_on_goal = Column(Integer)
    shots_off_goal = Column(Integer)
    total_shots = Column(Integer)
    blocked_shots = Column(Integer)
    shots_inside_box = Column(Integer)
    shots_outside_box = Column(Integer)
    fouls = Column(Integer)
    corner_kicks = Column(Integer)
    offsides = Column(Integer)
    ball_possession = Column(Float)
    yellow_cards = Column(Integer)
    red_cards = Column(Integer)
    goalkeeper_saves = Column(Integer)
    total_passes = Column(Integer)
    passes_accurate = Column(Integer)
    passes_pct = Column(Float)
    expected_goals = Column(Float)
    is_final = Column(Boolean, default=False)
    captured_at = Column(DateTime, default=datetime.utcnow)


class ApiFootballPrediction(Base):
    """Pre-match snapshot of api-football's own AI prediction. Captured ONCE per
    match in the 24h pre-kickoff window, then never re-fetched (their prediction
    doesn't update during the match)."""
    __tablename__ = "api_football_predictions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, unique=True, index=True)
    api_fixture_id = Column(Integer)
    winner_id = Column(Integer)
    winner_name = Column(String)
    winner_comment = Column(String)
    win_or_draw = Column(Boolean)
    under_over = Column(String)
    goals_home = Column(Float)         # avg expected goals
    goals_away = Column(Float)
    advice = Column(String)
    pct_home = Column(String)
    pct_draw = Column(String)
    pct_away = Column(String)
    # Comparison panel (all strings like "67%" because that's how the API returns them)
    comp_form_home = Column(String)
    comp_form_away = Column(String)
    comp_att_home = Column(String)
    comp_att_away = Column(String)
    comp_def_home = Column(String)
    comp_def_away = Column(String)
    comp_poisson_home = Column(String)
    comp_poisson_away = Column(String)
    comp_h2h_home = Column(String)
    comp_h2h_away = Column(String)
    comp_goals_home = Column(String)
    comp_goals_away = Column(String)
    comp_total_home = Column(String)
    comp_total_away = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow)


class MatchH2H(Base):
    """Historical head-to-head fixtures between any two teams we have ever queried.
    Stored forever — H2H only grows when teams play each other again. Indexed on
    (team1, team2) where team1_id < team2_id so the canonical key is order-agnostic."""
    __tablename__ = "match_h2h"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_fixture_id = Column(Integer, unique=True)
    team1_id = Column(Integer, nullable=False, index=True)   # smaller id
    team2_id = Column(Integer, nullable=False, index=True)   # larger id
    fixture_date = Column(DateTime)
    league_id = Column(Integer)
    league_name = Column(String)
    season = Column(Integer)
    home_team_id = Column(Integer)
    home_team_name = Column(String)
    away_team_id = Column(Integer)
    away_team_name = Column(String)
    home_score = Column(Integer)
    away_score = Column(Integer)
    venue = Column(String, nullable=True)
    status_short = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow)


class PlayerProfile(Base):
    """One canonical record per player we have ever seen. Refreshed only if name/
    photo/age changes. Drives the upcoming player narrative cards."""
    __tablename__ = "player_profiles"
    player_id = Column(Integer, primary_key=True)
    name = Column(String)
    firstname = Column(String)
    lastname = Column(String)
    age = Column(Integer)
    birth_date = Column(String)
    birth_place = Column(String)
    birth_country = Column(String)
    nationality = Column(String)
    height = Column(String)           # e.g. "180 cm"
    weight = Column(String)           # e.g. "75 kg"
    photo_url = Column(String)
    team_id = Column(Integer)
    team_name = Column(String)
    position = Column(String)
    captured_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PlayerTournamentStats(Base):
    """Per-player aggregated WC2026 stats. Recomputed from MatchEvent + MatchLineupPlayer
    after every FT — zero API cost. Replaces the costly /players/topscorers polling."""
    __tablename__ = "player_tournament_stats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_id = Column(Integer, nullable=False, index=True)
    player_name = Column(String)
    team_id = Column(Integer, index=True)
    team_name = Column(String)
    tournament = Column(String, default="WC2026", index=True)
    appearances = Column(Integer, default=0)
    minutes = Column(Integer, default=0)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    own_goals = Column(Integer, default=0)
    penalty_goals = Column(Integer, default=0)
    # Penalty TRACKING — every spot-kick attempt the player has taken,
    # including ones they put wide/over/saved. Lets us surface conversion
    # rates so that "Messi 2/3 from the spot at the WC" beats "Messi 2 pen
    # goals" for shootout-context betting. Regulation + shootout kept apart
    # because a 70% regulation kicker can still wobble in a shootout.
    penalty_attempts = Column(Integer, default=0)
    penalty_misses = Column(Integer, default=0)
    shootout_penalty_goals = Column(Integer, default=0)
    shootout_penalty_misses = Column(Integer, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)


class TeamSeasonStats(Base):
    """Per-team accumulated WC2026 form. Recomputed from MatchStatistics + Match
    results after every FT. The data behind the upcoming Bayesian λ shrinkage."""
    __tablename__ = "team_season_stats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_id = Column(Integer, index=True)
    team_code = Column(String, index=True)
    team_name = Column(String)
    tournament = Column(String, default="WC2026", index=True)
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    xg_for = Column(Float, default=0.0)
    xg_against = Column(Float, default=0.0)
    possession_avg = Column(Float)
    shots_total = Column(Integer, default=0)
    shots_on_target = Column(Integer, default=0)
    fouls = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    clean_sheets = Column(Integer, default=0)
    computed_at = Column(DateTime, default=datetime.utcnow)


class HarvestJob(Base):
    """Queue of api-football fetches to perform when we have spare quota.

    Workers pick the highest-priority `pending` job, fetch the configured endpoint
    with `params_json`, persist the response into HarvestRaw, then set status=done.
    Hard-floored by a daily quota guard so live polling is never starved."""
    __tablename__ = "harvest_jobs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String, nullable=False, index=True)   # e.g. "/players/squads"
    params_json = Column(String, nullable=False)             # JSON string of query params
    priority = Column(Integer, default=100, index=True)      # lower = sooner
    status = Column(String, default="pending", index=True)   # pending|in_progress|done|error|skipped
    scheduled_for = Column(DateTime, default=datetime.utcnow, index=True)
    attempted_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    response_size_bytes = Column(Integer, nullable=True)
    error_msg = Column(String, nullable=True)
    dedup_key = Column(String, unique=True, index=True)      # (endpoint + sorted params) hash so we never queue a duplicate


class HarvestRaw(Base):
    """The raw API response for every completed HarvestJob. Kept forever (compressed
    on disk if it gets big) so we can re-process into normalised tables whenever the
    schema evolves without re-paying the API cost."""
    __tablename__ = "harvest_raw"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=False, index=True)
    endpoint = Column(String, nullable=False)
    captured_at = Column(DateTime, default=datetime.utcnow)
    response_json = Column(String)                            # the literal JSON we got back
    status_code = Column(Integer)
    processed = Column(Boolean, default=False, index=True)  # has harvest_processor consumed this blob yet?


class ModelMulti(Base):
    """Model-curated multi bets the system auto-picks daily. Each is a 'Balanced'
    pick (combined prob + edge over market). Settled automatically when all legs
    complete. Tracked publicly so the running ROI is the credibility signal."""
    __tablename__ = "model_multis"
    id = Column(Integer, primary_key=True, autoincrement=True)
    generated_at = Column(DateTime, default=datetime.utcnow, index=True)
    label = Column(String)                            # e.g. "Brazil v Haiti BTTS + Over 2.5"
    kind = Column(String)                             # "sgm" (one match) | "cross" (multi-match)
    combined_prob = Column(Float)                     # model true joint prob
    combined_fair_odds = Column(Float)                # 1 / combined_prob
    combined_book_odds = Column(Float)                # product of best-available per-leg book prices
    ev_pct = Column(Float)                            # (prob * book_odds - 1) * 100
    kelly_pct = Column(Float)                         # quarter-Kelly stake recommendation
    status = Column(String, default="pending", index=True)   # pending|won|lost|void
    settled_at = Column(DateTime, nullable=True)
    profit_loss_units = Column(Float, nullable=True)  # +X units won at 1-unit stake, -1 if lost
    notes = Column(String, nullable=True)


class ModelMultiLeg(Base):
    """One leg of a model-picked multi. Linked to the source match so we can
    settle when results land."""
    __tablename__ = "model_multi_legs"
    id = Column(Integer, primary_key=True, autoincrement=True)
    multi_id = Column(Integer, nullable=False, index=True)
    leg_order = Column(Integer)
    match_id = Column(String, nullable=False, index=True)
    market = Column(String, nullable=False)
    market_label = Column(String)                      # human-readable
    model_prob = Column(Float)
    market_implied_prob = Column(Float, nullable=True) # devig consensus
    book_odds = Column(Float, nullable=True)           # the best book price we picked
    book_name = Column(String, nullable=True)          # which bookmaker offered the best
    leg_status = Column(String, default="pending")     # pending|won|lost|void
    settled_at = Column(DateTime, nullable=True)


class TeamInjury(Base):
    """Snapshot of injured/suspended players for a team, captured by the
    injuries fetcher. One row per (team_code, player_id). 'severity' is a
    rough estimate from the API (out/doubtful/questionable/probable)."""
    __tablename__ = "team_injuries"
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_code = Column(String, nullable=False, index=True)
    api_player_id = Column(Integer, nullable=True, index=True)
    player_name = Column(String)
    reason = Column(String)         # e.g. "Knee injury", "Yellow card suspension"
    severity = Column(String)       # "out" | "doubtful" | "questionable" | "probable"
    captured_at = Column(DateTime, default=datetime.utcnow)
    last_seen_at = Column(DateTime, default=datetime.utcnow)


class ModelCalibrationLog(Base):
    """Per-match calibration measurement: how close was the pre-kickoff
    probability to the actual outcome? Computed once on settlement. Drives
    the rolling Brier / log-loss chart that shows the model getting sharper
    (or not) as the tournament progresses."""
    __tablename__ = "model_calibration_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    match_id = Column(String, nullable=False, unique=True, index=True)
    settled_at = Column(DateTime, default=datetime.utcnow)
    home_score = Column(Integer)
    away_score = Column(Integer)
    pre_p_home = Column(Float)
    pre_p_draw = Column(Float)
    pre_p_away = Column(Float)
    brier_1x2 = Column(Float)          # 1X2 Brier on this single match
    log_loss_1x2 = Column(Float)        # log loss
    favorite_correct = Column(Integer)  # 1 if our pre-kickoff favourite won, 0 if not


class PlayerHistory(Base):
    """Per-match stats for a player in a specific fixture. One row per
    (api_player_id, api_fixture_id). Drawn from api-football's
    /players?team=X&season=Y and /fixtures/players?fixture=X responses."""
    __tablename__ = "player_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_player_id = Column(Integer, nullable=False, index=True)
    api_fixture_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=True)  # our internal match id if resolvable
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    minutes = Column(Integer, default=0)
    rating = Column(Float, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class FixtureArchive(Base):
    """Per-team match statistics from /fixtures/statistics. One row per
    (api_fixture_id, team_api_id). Drives xG-based model upgrades."""
    __tablename__ = "fixture_archive"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_fixture_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=True)
    team_api_id = Column(Integer, nullable=False, index=True)
    possession = Column(Float, nullable=True)
    shots_total = Column(Integer, nullable=True)
    shots_on_target = Column(Integer, nullable=True)
    shots_off_target = Column(Integer, nullable=True)
    shots_insidebox = Column(Integer, nullable=True)
    shots_outsidebox = Column(Integer, nullable=True)
    shots_blocked = Column(Integer, nullable=True)
    xg = Column(Float, nullable=True)
    passes_total = Column(Integer, nullable=True)
    pass_accuracy = Column(Integer, nullable=True)
    fouls = Column(Integer, nullable=True)
    yellow_cards = Column(Integer, nullable=True)
    red_cards = Column(Integer, nullable=True)
    corners = Column(Integer, nullable=True)
    offsides = Column(Integer, nullable=True)
    goalkeeper_saves = Column(Integer, nullable=True)
    goals_prevented = Column(Float, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class FixtureLineup(Base):
    """Per-player per-fixture lineup data from /fixtures/lineups.
    One row per (api_fixture_id, team_api_id, player_api_id)."""
    __tablename__ = "fixture_lineups"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_fixture_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=True, index=True)
    team_api_id = Column(Integer, nullable=False, index=True)
    team_name = Column(String, nullable=True)
    player_api_id = Column(Integer, nullable=False, index=True)
    player_name = Column(String, nullable=True)
    player_number = Column(Integer, nullable=True)
    position = Column(String, nullable=True)
    is_starter = Column(Boolean, default=False)
    grid_position = Column(String, nullable=True)
    minutes_played = Column(Integer, default=0)
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    shots_total = Column(Integer, nullable=True)
    shots_on = Column(Integer, nullable=True)
    passes_total = Column(Integer, nullable=True)
    passes_accuracy = Column(Integer, nullable=True)
    tackles_total = Column(Integer, nullable=True)
    dribbles_attempts = Column(Integer, nullable=True)
    duels_won = Column(Integer, nullable=True)
    rating = Column(Float, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class TeamSeasonProfile(Base):
    """Per-team per-league-season profile from /teams/statistics.
    Cards by minute band, formations, goals by period, clean sheets."""
    __tablename__ = "team_season_profiles"
    id = Column(Integer, primary_key=True, autoincrement=True)
    team_api_id = Column(Integer, nullable=False, index=True)
    team_name = Column(String, nullable=True)
    league_id = Column(Integer, nullable=False, index=True)
    league_name = Column(String, nullable=True)
    season = Column(Integer, nullable=False)
    matches_played_total = Column(Integer, default=0)
    matches_played_home = Column(Integer, default=0)
    matches_played_away = Column(Integer, default=0)
    wins_home = Column(Integer, default=0)
    wins_away = Column(Integer, default=0)
    draws_home = Column(Integer, default=0)
    draws_away = Column(Integer, default=0)
    loses_home = Column(Integer, default=0)
    loses_away = Column(Integer, default=0)
    goals_for_total = Column(Integer, default=0)
    goals_for_avg = Column(Float, nullable=True)
    goals_against_total = Column(Integer, default=0)
    goals_against_avg = Column(Float, nullable=True)
    clean_sheets_total = Column(Integer, default=0)
    failed_to_score_total = Column(Integer, default=0)
    avg_possession = Column(Float, nullable=True)
    yellow_cards_per_game = Column(Float, nullable=True)
    red_cards_per_game = Column(Float, nullable=True)
    penalties_scored_pct = Column(Float, nullable=True)
    formations_json = Column(String, nullable=True)
    goals_for_minute_json = Column(String, nullable=True)
    goals_against_minute_json = Column(String, nullable=True)
    cards_yellow_minute_json = Column(String, nullable=True)
    cards_red_minute_json = Column(String, nullable=True)
    biggest_win_home = Column(String, nullable=True)
    biggest_win_away = Column(String, nullable=True)
    biggest_loss_home = Column(String, nullable=True)
    biggest_loss_away = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class StandingsHistory(Base):
    """League standings snapshot per team per season."""
    __tablename__ = "standings_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    league_id = Column(Integer, nullable=False, index=True)
    season = Column(Integer, nullable=False)
    team_api_id = Column(Integer, nullable=False, index=True)
    team_name = Column(String, nullable=True)
    rank = Column(Integer, default=0)
    points = Column(Integer, default=0)
    goals_diff = Column(Integer, default=0)
    form = Column(String, nullable=True)
    matches_played = Column(Integer, default=0)
    wins = Column(Integer, default=0)
    draws = Column(Integer, default=0)
    losses = Column(Integer, default=0)
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    group_name = Column(String, nullable=True)
    status = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class CoachProfile(Base):
    """Coach info from /coachs endpoint."""
    __tablename__ = "coach_profiles"
    api_coach_id = Column(Integer, primary_key=True)
    name = Column(String, nullable=True)
    firstname = Column(String, nullable=True)
    lastname = Column(String, nullable=True)
    age = Column(Integer, nullable=True)
    birth_date = Column(String, nullable=True)
    birth_place = Column(String, nullable=True)
    birth_country = Column(String, nullable=True)
    nationality = Column(String, nullable=True)
    height = Column(String, nullable=True)
    weight = Column(String, nullable=True)
    photo_url = Column(String, nullable=True)
    team_api_id = Column(Integer, nullable=True, index=True)
    team_name = Column(String, nullable=True)
    career_json = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class PlayerTransfer(Base):
    """Player transfer history from /transfers endpoint."""
    __tablename__ = "player_transfers"
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_api_id = Column(Integer, nullable=False, index=True)
    player_name = Column(String, nullable=True)
    transfer_date = Column(DateTime, nullable=True)
    from_team_id = Column(Integer, nullable=True)
    from_team_name = Column(String, nullable=True)
    to_team_id = Column(Integer, nullable=True)
    to_team_name = Column(String, nullable=True)
    transfer_type = Column(String, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class PlayerSidelined(Base):
    """Injuries and suspensions from /sidelined endpoint."""
    __tablename__ = "player_sidelined"
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_api_id = Column(Integer, nullable=False, index=True)
    player_name = Column(String, nullable=True)
    team_api_id = Column(Integer, nullable=True, index=True)
    team_name = Column(String, nullable=True)
    type = Column(String, nullable=True)
    reason = Column(String, nullable=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)


class PlayerSeasonStats(Base):
    """Per-player per-league-season aggregate stats. One row per
    (player_api_id, team_api_id, league_id, season). Computed from
    /players and /fixtures/players responses."""
    __tablename__ = "player_season_stats"
    id = Column(Integer, primary_key=True, autoincrement=True)
    player_api_id = Column(Integer, nullable=False, index=True)
    team_api_id = Column(Integer, nullable=False, index=True)
    league_id = Column(Integer, nullable=False, index=True)
    league_name = Column(String, nullable=True)
    season = Column(Integer, nullable=False)
    appearances = Column(Integer, default=0)
    minutes = Column(Integer, default=0)
    position = Column(String, nullable=True)
    rating = Column(Float, nullable=True)
    goals_total = Column(Integer, default=0)
    assists_total = Column(Integer, default=0)
    shots_total = Column(Integer, default=0)
    shots_on = Column(Integer, default=0)
    passes_total = Column(Integer, default=0)
    passes_accuracy = Column(Integer, nullable=True)
    tackles_total = Column(Integer, default=0)
    dribbles_attempts = Column(Integer, default=0)
    duels_won = Column(Integer, default=0)
    yellow_cards = Column(Integer, default=0)
    red_cards = Column(Integer, default=0)
    penalty_scored = Column(Integer, default=0)
    penalty_missed = Column(Integer, default=0)
    penalty_won = Column(Integer, default=0)
    captured_at = Column(DateTime, default=datetime.utcnow)


class HarvestErrorLog(Base):
    """Diagnostic log for harvest jobs that error out. One row per error so we
    can spot systematic failures (e.g. a league that was never seeded)."""
    __tablename__ = "harvest_error_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(Integer, nullable=True, index=True)
    endpoint = Column(String, nullable=True)
    error_type = Column(String, nullable=True)
    error_msg = Column(String, nullable=True)
    logged_at = Column(DateTime, default=datetime.utcnow, index=True)


class SettingsKV(Base):
    """Tiny runtime key/value store for operator toggles that must survive a
    restart without a redeploy (e.g. pausing the harvester from the admin UI).

    Kept deliberately generic: a single value column (TEXT) holds whatever the
    caller wants — JSON, a number, a flag. The admin UI is the only writer.
    """
    __tablename__ = "settings_kv"
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
