import type {
  Match,
  MatchPrediction,
  Market,
  ValueOpportunity,
  Arb,
  AccaCombo,
  HistoryEntry,
  HistoryStats,
  Match3Alert,
  GroupStanding,
  TeamProfile,
  Calibration,
  TournamentProjection,
  MarketsSheet,
  RadarData,
  MultiAnalysis,
  MultiLegInput,
} from "./types"

const BASE =
  typeof window === "undefined"
    ? (process.env.BACKEND_URL ?? "http://wc26-backend:8000")
    : (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000")

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { next: { revalidate: 60 } })
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`)
  return res.json()
}

export const api = {
  matches: (group?: string, matchday?: number) => {
    const params = new URLSearchParams()
    if (group) params.set("group", group)
    if (matchday) params.set("matchday", String(matchday))
    const qs = params.toString()
    return get<Match[]>(`/matches${qs ? "?" + qs : ""}`)
  },
  match: (id: string) => get<Match>(`/matches/${id}`),
  prediction: (id: string) => get<MatchPrediction>(`/matches/${id}/prediction`),
  markets: (id: string) => get<MarketsSheet>(`/matches/${id}/markets`),
  value: () => get<ValueOpportunity[]>("/betting/value"),
  arbs: () => get<Arb[]>("/betting/arbs"),
  acca: (k: number, matchday?: number) => get<AccaCombo[]>(`/betting/acca?k=${k}${matchday ? "&matchday=" + matchday : ""}`),
  history: () => get<HistoryEntry[]>("/history"),
  historyStats: () => get<HistoryStats>("/history/stats"),
  calibration: () => get<Calibration>("/history/calibration"),
  // Rolling-vs-all-time Brier delta from the calibration logger. Surfaces the
  // "is the model getting sharper as the tournament progresses?" signal.
  calibrationTrend: () => get<{
    total: number;
    all_time_brier?: number;
    recent_brier?: number;
    all_time_hit_rate?: number;
    recent_hit_rate?: number;
    window?: number;
    trend_brier?: number;
  }>("/model/calibration"),
  tournament: () => get<TournamentProjection>("/tournament/projections"),
  bracketLive: () => get<any>("/tournament/bracket-live"),
  scoreboard: () => get<any>("/history/scoreboard"),
  scoreboardTournament: () => get<any>("/history/scoreboard/tournament"),
  scorers: () => get<any>("/extras/topscorers"),
  h2h: (matchId: string) => get<any>(`/extras/matches/${matchId}/h2h`),
  upcoming: () => get<any>("/live/upcoming?n=6"),
  recent: () => get<any>("/live/recent?n=3"),
  recentEnriched: () => get<{
    matches: Array<{
      id: string;
      home_name: string; away_name: string;
      home_flag: string | null; away_flag: string | null;
      home_score: number | null; away_score: number | null;
      scorer_line: string;
      red_cards: number;
    }>;
  }>("/live/recent-enriched?n=4"),
  liveHub: () => get<any>("/live/hub/enriched"),
  matchRecap: (id: string) => get<{
    match_id: string;
    status: string;
    is_complete: boolean;
    has_content: boolean;
    score: { home: number | null; away: number | null } | null;
    kickoff: string | null;
    venue: string | null;
    home: {
      code: string | null; name: string; flag_url: string | null;
      stats: any | null;
      lineup: { formation: string | null; coach: string | null; starters: any[]; bench: any[] } | null;
    };
    away: {
      code: string | null; name: string; flag_url: string | null;
      stats: any | null;
      lineup: { formation: string | null; coach: string | null; starters: any[]; bench: any[] } | null;
    };
    events: Array<{
      minute: number; elapsed: number | null; extra: number | null;
      type: string; detail: string;
      player_id: number | null; player_name: string | null;
      assist_name: string | null;
      team_side: "home" | "away" | null;
      team_name: string | null;
    }>;
    motm: { player_id: number | null; name: string; goals: number; side: "home" | "away" | null; team_name: string | null } | null;
  }>(`/matches/${id}/recap`),
  // Tiny site-wide live ticker payload — polled every 30s by the persistent
  // TopBar banner that pulls users to /live when matches are in play.
  storylines: () => get<{
    cards: Array<{
      kind: "upset" | "goalfest" | "player_haul" | "live_now";
      match_id: string;
      title: string;
      headline: string;
      score?: string;
      gap?: number;
      total_goals?: number;
      elapsed_min?: number;
      player_id?: number;
      team_name?: string;
      goals?: number;
    }>;
    window: "today" | "recent";
  }>("/live/storylines"),
  liveSummary: () => get<{
    live_count: number;
    live: Array<{
      id: string;
      home: { code: string | null; name: string; flag_url: string | null };
      away: { code: string | null; name: string; flag_url: string | null };
      home_score: number;
      away_score: number;
      elapsed_min: number;
      status: string;
    }>;
    next: {
      id: string;
      home: { code: string | null; name: string; flag_url: string | null };
      away: { code: string | null; name: string; flag_url: string | null };
      kickoff: string | null;
      minutes_away: number | null;
    } | null;
  }>("/live/summary"),
  scenarios: (group?: string) => {
    const qs = group ? `?group=${encodeURIComponent(group)}` : ""
    return get<any>(`/groups/scenarios${qs}`)
  },
  news: (teamCode: string) =>
    get<{ headline: string; source: string; url: string }[]>(`/news/${teamCode}`),
  match3: () => get<Match3Alert[]>("/match3"),
  groups: () => get<GroupStanding[]>("/groups"),
  teamProfile: (code: string) => get<TeamProfile>(`/teams/${code}/profile`),
  // Rich squad — PlayerProfile + season stats joined. Powers the photo grid
  // on /team/{code}. Returns empty {players:[]} for teams not yet harvested.
  squadRich: (code: string) => get<{
    total: number;
    players: Array<{
      player_id: number;
      name: string;
      position: string;
      age: number | null;
      nationality: string | null;
      height: string | null;
      weight: string | null;
      photo_url: string | null;
      stats: {
        appearances: number; goals: number; assists: number; minutes: number;
        yellow_cards: number; red_cards: number;
      } | null;
    }>;
  }>(`/teams/${code}/squad-rich`),
  playerProfile: (id: number) => get<{
    player: {
      id: number; name: string; firstname: string | null; lastname: string | null;
      age: number | null; position: string | null; nationality: string | null;
      height: string | null; weight: string | null; photo_url: string | null;
      team_id: number | null; team_name: string | null;
      nation_code: string | null; nation_name: string | null; nation_flag: string | null;
    };
    totals: { appearances: number; goals: number; assists: number; minutes: number; yellow_cards: number; red_cards: number };
    career_stats: Array<{
      team_id: number; team_name: string | null; tournament: string | null;
      appearances: number; goals: number; assists: number; minutes: number;
      yellow_cards: number; red_cards: number;
    }>;
    recent_matches: Array<{
      api_fixture_id: number; match_id: string | null;
      goals: number; assists: number; minutes: number; rating: number | null;
    }>;
  }>(`/players-api/${id}/profile`),
  teamRecentForm: (code: string) => get<{
    form: Array<{
      match_id: string;
      opponent_code: string;
      score: string;
      result: "W" | "L" | "D" | null;
      kickoff: string | null;
      venue: "H" | "A";
    }>;
  }>(`/teams/${code}/recent-form`),
  radar: () => get<RadarData>("/teams/radar"),
  // The custom-multi analyzer is invoked from a client component, so the request must
  // hit a same-origin path the browser can resolve (NEXT_PUBLIC_API_URL is the
  // Fetch best available bookmaker prices for a list of matches. Used by the
  // bet builder to suggest a fillable price next to each leg.
  bestPrices: async (matchIds: string[]): Promise<{ by_match: Record<string, Record<string, { best_price: number | null; best_book: string | null }>> }> => {
    const res = await fetch("/api/proxy/best-prices", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ match_ids: matchIds }),
      cache: "no-store",
    })
    return res.json()
  },

  // docker-internal backend hostname in prod). Goes via the Next API proxy route.
  analyzeMulti: async (
    legs: MultiLegInput[],
    opts?: { slip_book_price?: number | null; objective?: "solid" | "balanced" | "bold" | "ev" | "land" },
  ): Promise<MultiAnalysis> => {
    const res = await fetch("/api/proxy/analyze-multi", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        legs,
        slip_book_price: opts?.slip_book_price ?? null,
        objective: opts?.objective ?? "balanced",
      }),
      cache: "no-store",
    })
    if (!res.ok) throw new Error(`Analyze failed (${res.status})`)
    return res.json()
  },
}
