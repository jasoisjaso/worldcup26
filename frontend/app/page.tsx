import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { MatchCard } from "@/components/match/MatchCard"
import { HomeHero } from "@/components/home/HomeHero"
import { api } from "@/lib/api"
import type { Match, MatchPrediction, TournamentProjection, HistoryStats } from "@/lib/types"

const MATCHDAYS = [1, 2, 3] as const
const GROUPS = ["All", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
type Matchday = (typeof MATCHDAYS)[number]

/**
 * Default landing matchday picks the most "alive" matchday so we never open on a fully
 * played-out round. Preference order, evaluated against `now`:
 *
 *   1. The matchday with the most matches still upcoming (kickoff > now and not complete).
 *      Ties broken by the soonest kickoff so the page is freshest.
 *   2. If every match across every matchday is complete, the highest matchday number
 *      (so users land on the most recent results, not the very first game).
 *   3. Otherwise — pre-tournament with no data — MD1.
 */
function pickActiveMatchday(matches: Match[], now = Date.now()): Matchday {
  if (matches.length === 0) return 1

  // Plain array of buckets keeps tsconfig happy (no Map iterator spread).
  const buckets: { md: Matchday; upcoming: number; nextKickoff: number }[] =
    MATCHDAYS.map((md) => ({ md, upcoming: 0, nextKickoff: Infinity }))

  let anyUpcoming = false
  for (const m of matches) {
    const md = m.matchday as Matchday
    const bucket = buckets.find((b) => b.md === md)
    if (!bucket) continue
    const ko = new Date(m.kickoff).getTime()
    if (m.status !== "complete" && ko > now) {
      bucket.upcoming += 1
      bucket.nextKickoff = Math.min(bucket.nextKickoff, ko)
      anyUpcoming = true
    }
  }

  if (anyUpcoming) {
    return [...buckets].sort(
      (a, b) => (b.upcoming - a.upcoming) || (a.nextKickoff - b.nextKickoff),
    )[0].md
  }
  return 3
}

function sanitiseGroup(raw: string | undefined): string {
  return raw && GROUPS.includes(raw) ? raw : "All"
}

function sanitiseMatchday(raw: string | undefined): Matchday | null {
  const n = raw ? Number.parseInt(raw, 10) : NaN
  return Number.isFinite(n) && (MATCHDAYS as readonly number[]).includes(n) ? (n as Matchday) : null
}

async function getMatchesWithPredictions(matchday: number): Promise<(Match & { prediction?: MatchPrediction })[]> {
  const matches = await api.matches(undefined, matchday)
  const predictions = await Promise.allSettled(matches.map((m) => api.prediction(m.id)))
  return matches.map((match, i) => ({
    ...match,
    prediction: predictions[i].status === "fulfilled" ? predictions[i].value : undefined,
  }))
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: { group?: string; matchday?: string }
}) {
  const explicitMd = sanitiseMatchday(searchParams.matchday)
  const groupFilter = sanitiseGroup(searchParams.group)

  let matchday: Matchday
  let matches: (Match & { prediction?: MatchPrediction })[]

  if (explicitMd) {
    matchday = explicitMd
    matches = await getMatchesWithPredictions(matchday)
  } else {
    const all = await api.matches()
    matchday = pickActiveMatchday(all)
    matches = await getMatchesWithPredictions(matchday)
  }

  let proj: TournamentProjection | null = null
  let stats: HistoryStats | null = null
  try {
    ;[proj, stats] = await Promise.all([api.tournament(), api.historyStats()])
  } catch {
    /* hero degrades gracefully */
  }

  const filtered = groupFilter !== "All" ? matches.filter((m) => m.group === groupFilter) : matches
  const valueCount = matches.filter((m) => m.prediction?.markets.some((mk) => mk.ev > 0.05)).length

  return (
    <>
      <TopBar
        title={`Group Stage — Matchday ${matchday}`}
        subtitle={`${matches.length} matches · ${valueCount} with value picks`}
      />

      <div className="px-3 sm:px-6 py-4 sm:py-5">
        {(proj || stats) && (
          <div className="mb-5">
            <HomeHero proj={proj} stats={stats} />
          </div>
        )}

        <div className="flex gap-2 mb-4">
          {MATCHDAYS.map((md) => (
            <Link
              key={md}
              href={`/?matchday=${md}${groupFilter !== "All" ? `&group=${groupFilter}` : ""}`}
              prefetch={false}
              className={[
                "px-3 py-1.5 rounded-lg text-[12px] font-semibold border transition-colors",
                matchday === md
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Matchday {md}
            </Link>
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5 mb-5 items-center">
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mr-1">Group</span>
          {GROUPS.map((g) => (
            <Link
              key={g}
              href={`/?matchday=${matchday}${g !== "All" ? `&group=${g}` : ""}`}
              prefetch={false}
              className={[
                "px-2.5 py-1 rounded-md text-[11px] font-semibold border transition-colors",
                groupFilter === g
                  ? "bg-emerald-950 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {g}
            </Link>
          ))}
        </div>

        <div>
          {filtered.map((match) => (
            <MatchCard key={match.id} match={match} prediction={match.prediction} from="/" />
          ))}
          {filtered.length === 0 && (
            <p className="text-slate-500 text-sm py-8 text-center">No matches found for this filter.</p>
          )}
        </div>
      </div>
    </>
  )
}
