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
  bookmaker_odds: number
  ev: number
  is_positive_ev: boolean
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
  prediction?: MatchPrediction
}

export interface HistoryEntry {
  id: number
  match_id: string
  match_label: string
  home_code: string
  away_code: string
  market: string
  market_label: string
  our_probability: number
  bookmaker_odds: number
  ev: number
  logged_at: string
  actual_result?: string
  correct?: boolean
}

export interface HistoryStats {
  accuracy: number
  avg_ev: number
  roi: number
  total: number
  correct: number
}
