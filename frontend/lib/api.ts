import type {
  Match,
  MatchPrediction,
  Market,
  ValueOpportunity,
  AccaCombo,
  HistoryEntry,
  HistoryStats,
  Match3Alert,
  GroupStanding,
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
  value: () => get<ValueOpportunity[]>("/betting/value"),
  acca: (k: number) => get<AccaCombo[]>(`/betting/acca?k=${k}`),
  history: () => get<HistoryEntry[]>("/history"),
  historyStats: () => get<HistoryStats>("/history/stats"),
  news: (teamCode: string) =>
    get<{ headline: string; source: string; url: string }[]>(`/news/${teamCode}`),
  match3: () => get<Match3Alert[]>("/match3"),
  groups: () => get<GroupStanding[]>("/groups"),
}
