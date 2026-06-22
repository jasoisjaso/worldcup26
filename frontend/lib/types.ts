export interface Team {
  code: string
  name: string
  fifa_code: string
  elo: number
  fifa_ranking: number | null
  flag_url: string
  primary_color: string
}

export interface WhyFactor {
  label: string
  direction: "positive" | "negative" | "neutral"
}

export interface ScoreLine {
  home: number
  away: number
  probability: number
}

export interface Market {
  market: string
  label: string
  our_prob: number
  model_prob?: number
  market_implied?: number
  reliability?: "solid" | "speculative" | "longshot"
  bookmaker_odds: number
  ev: number
  is_positive_ev: boolean
}

export interface ValueOpportunity extends Market {
  match_id: string
  match_label: string
  group: string
  matchday: number
  kickoff: string | null
  kelly_pct: number
  best_price?: number | null
  best_book?: string | null
  ev_best?: number
}

export interface ArbLeg {
  market: string
  best_price: number
  best_book: string | null
}

export interface Arb {
  match_id: string
  match_label: string
  kickoff: string | null
  market: string
  sum_implied: number
  margin: number
  legs: ArbLeg[]
}

export interface AccaCombo {
  legs: ValueOpportunity[]
  combined_odds: number
  combined_probability: number
  ev: number
  kelly_pct?: number
}

export interface FormResult {
  result: "W" | "D" | "L"
  opponent?: string
}

export interface MatchPrediction {
  match_id: string
  home_win: number
  draw: number
  away_win: number
  over_2_5: number
  under_2_5: number
  btts: number
  top_scores: ScoreLine[]
  markets: Market[]
  why_factors: WhyFactor[]
  lambda_home: number
  lambda_away: number
  expected_corners: number
  expected_cards: number
  context?: {
    harvested?: {
      home: TeamHarvestedSnapshot | null
      away: TeamHarvestedSnapshot | null
    }
  }
}

export interface TeamHarvestedSnapshot {
  xg_per_match?: number
  xg_sample?: number
  corners_per_match?: number
  xg_trend?: "rising" | "falling" | "flat"
}

export interface Match {
  id: string
  group: string
  matchday: number
  kickoff: string
  venue: string
  status: "upcoming" | "live" | "complete"
  home: Team
  away: Team
  actual_score?: { home: number; away: number }
  // Half-time score — null until the backfill job populates it from the
  // harvested /fixtures blobs. Renders as "HT: 0-2" alongside the FT line.
  ht_score?: { home: number; away: number } | null
  prediction?: MatchPrediction
}

export interface HistoryEntry {
  id: number
  match_id: string
  match_label: string
  home_code: string
  away_code: string
  home_name: string
  away_name: string
  home_flag_url: string
  away_flag_url: string
  market: string
  market_label: string
  pick_label: string
  our_probability: number
  bookmaker_odds: number
  ev: number
  closing_odds?: number | null
  clv?: number | null
  logged_at: string
  actual_result?: string
  correct?: boolean | null
}

export interface HistoryStats {
  accuracy: number
  avg_ev: number
  roi: number
  total: number
  correct: number
  settled?: number
  brier?: number
  log_loss?: number
  ece?: number
  edge_signal?: "building" | "beating" | "lagging"
  roi_ci?: number
  roi_significant?: boolean
  bets_to_significance?: number
  clv_n?: number
  avg_clv?: number
  clv_beat_close_rate?: number
  clv_beat_lo?: number
  clv_beat_hi?: number
  clv_t?: number
  tier_record?: Record<string, { n: number; correct: number; rate: number }>
  note?: string
}

export interface ReliabilityBin {
  bucket: string
  confidence: number
  frequency: number
  n: number
}

export interface MarketCalibration {
  n: number
  rps?: number
  brier: number
  log_loss?: number
  ece: number
  reliability: ReliabilityBin[]
}

export interface Calibration {
  n: number
  rps?: number
  log_loss?: number
  brier?: number
  ece_winner?: number
  reliability_winner?: ReliabilityBin[]
  over_2_5_brier?: number | null
  by_market?: {
    result_1x2?: MarketCalibration
    over_under_2_5?: MarketCalibration | null
    btts?: MarketCalibration | null
  }
  by_model_version?: Record<string, { rps: number; n: number }>
  note?: string
}

export interface TournamentTeam {
  code: string
  name: string
  group: string
  p_first: number
  p_second: number
  p_third: number
  p_third_qualify: number
  p_top2: number
  p_advance: number
  exp_points: number
  exp_gd: number
  exp_gf: number
  flag_url: string
  primary_color: string
  // populated by the knockout simulation
  p_r16?: number
  p_quarter?: number
  p_semi?: number
  p_final?: number
  p_title?: number
}

export interface BracketTeamRef {
  code: string
  p: number
}
export interface BracketMatch {
  match: number
  teams: BracketTeamRef[]
  home_rule?: string
  away_rule?: string
  home_src?: string
  away_src?: string
}
export interface BracketRound {
  name: string
  matches: BracketMatch[]
}
export interface Bracket {
  rounds: BracketRound[]
  third_place: BracketTeamRef[]
}

export interface TournamentProjection {
  n_sims: number
  model_version: string
  completed_matches: number
  teams: TournamentTeam[]
  has_knockout?: boolean
  bracket?: Bracket
}

export interface Match3Alert {
  match_id: string
  group: string
  kickoff: string | null
  match_label: string
  rotation_team: string
  rotation_status: string
  needs_result_team: string
  warning: string
}

export interface MarketOutcome {
  key: string
  label: string
  prob: number
  fair_odds: number | null
}

export interface MarketGroup {
  key: string
  name: string
  outcomes: MarketOutcome[]
  // Peripheral markets (corners, cards) carry these — present only for
  // groups that come from harvested fixture-stat averages instead of the
  // Dixon-Coles goal grid. FE renders a "low sample" caveat when set.
  indicative?: boolean
  confidence?: "ok" | "low" | "very_low"
  sample_size?: number
  expected_total?: number
}

export interface ScoreGrid {
  grid: number[][]
  max: number
  peak: number
}

export interface RadarTeam {
  code: string
  name: string
  flag_url: string
  primary_color: string
  values: Record<string, number>
}

export interface RadarData {
  axes: string[]
  teams: Record<string, RadarTeam>
}

export interface MarketsSheet {
  match_id?: string
  lambda_home: number
  lambda_away: number
  expected_total: number
  score_grid?: ScoreGrid
  groups: MarketGroup[]
}

export interface FormRow {
  match_id: string
  opponent_code: string
  opponent_name: string
  score: string
  result: "W" | "L" | "D" | null
  kickoff: string | null
  venue: "H" | "A"
}

export interface TeamSeasonStats {
  matches_sampled: number
  goals_per_match: number | null
  conceded_per_match: number | null
  btts_pct: number | null
  cs_pct: number | null
  // From FixtureArchive (may be missing when no archived fixtures yet)
  corners_per_match?: number | null
  yellow_per_match?: number | null
  shots_on_target_per_match?: number | null
  xg_per_match?: number | null
  possession_avg?: number | null
  archive_matches_sampled?: number
}

export interface H2HSummary {
  meetings: number
  home_wins: number
  draws: number
  away_wins: number
  agg_goals_per_meeting: number | null
  last: string | null
}

export interface AbsenceEntry {
  name: string | null
  reason: string
  count: number
}

export interface ModelSwingFromAbsences {
  home_pp: number
  away_pp: number
}

export interface PreMatchContext {
  match_id: string
  stakes: string
  home_form: FormRow[]
  away_form: FormRow[]
  home_absences: AbsenceEntry[]
  away_absences: AbsenceEntry[]
  season_stats: {
    home: TeamSeasonStats
    away: TeamSeasonStats
  }
  h2h_summary: H2HSummary
  model_swing_from_absences: ModelSwingFromAbsences | { error: string } | null
}

export interface TeamStanding {
  code: string
  name: string
  flag_url: string
  primary_color: string
  played: number
  won: number
  drawn: number
  lost: number
  gf: number
  ga: number
  gd: number
  points: number
}

export interface GroupStanding {
  group: string
  teams: TeamStanding[]
}

export interface SquadPlayer {
  id: number | null
  name: string
  position: string
  number: number | null
  photo: string
}

export interface TeamFixture {
  match_id: string
  opponent_code: string
  opponent: string
  opponent_flag: string
  is_home: boolean
  kickoff: string | null
  group: string
  matchday: number
}

export interface MultiAnalysisLeg {
  match_id: string
  match_label: string
  market: string
  label: string
  model_prob: number | null
  market_implied: number | null
  book_price: number | null
  ev_leg: number | null
  edge_flag: "edge" | "no_edge" | "anti_edge" | "unknown"
}

export interface MultiAnalysisPerMatch {
  match_id: string
  legs_in_match: number
  joint_prob_from_grid: number
  naive_product_in_match: number
  correlation_effect: number
}

export interface MultiSuggestion {
  kind: "swap" | "drop" | "replace_with_value" | "already_optimal"
  reason: string
  extra?: Record<string, unknown>
  before: {
    combined_probability: number | null
    fair_combined_odds: number | null
    ev: number | null
  }
  after?: {
    combined_probability: number | null
    fair_combined_odds: number | null
    ev: number | null
    ev_assumes_same_vig?: boolean
  }
  new_legs?: { match_id: string; market: string; label: string }[]
}

export interface MultiAnalysis {
  legs: MultiAnalysisLeg[]
  per_match: MultiAnalysisPerMatch[]
  combined_probability: number | null
  naive_product_all_legs: number
  fair_combined_odds: number | null
  slip_book_price: number | null
  ev: number | null
  warnings: string[]
  suggestion: MultiSuggestion | null
  objective: string
  error?: string
}

export interface MultiLegInput {
  match_id: string
  market: string
  book_price?: number | null
}

export interface TeamProfile {
  code: string
  name: string
  flag_url: string
  primary_color: string
  elo: number
  fifa_ranking: number | null
  manager: string
  set_piece_attack: number
  set_piece_defense: number
  squad: SquadPlayer[]
  upcoming_fixtures: TeamFixture[]
}
