import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { MatchCard } from "@/components/match/MatchCard"
import { HomeHero } from "@/components/home/HomeHero"
import { StorylinesStrip } from "@/components/home/StorylinesStrip"
import { LoudestTakes } from "@/components/home/LoudestTakes"
import { NotificationBell } from "@/components/common/NotificationBell"
import { api } from "@/lib/api"
import type { Match, MatchPrediction, TournamentProjection, HistoryStats } from "@/lib/types"

const MATCHDAYS = [1, 2, 3] as const
const GROUPS = ["All", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
type Matchday = (typeof MATCHDAYS)[number]

/**
 * Default landing matchday picks the "live" round — the one with the soonest next
 * kickoff. With 3 matchdays back-to-back, a later round usually has MORE upcoming
 * matches but they're still days away; users care about what's playing today, not
 * what starts next week. Preference order, evaluated against `now`:
 *
 *   1. The matchday whose next-upcoming kickoff is soonest. Ties broken by the
 *      higher count of upcoming matches (fresher round wins).
 *   2. If every match across every matchday is complete, the highest matchday
 *      number (so users land on the most recent results, not the very first game).
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
      (a, b) => (a.nextKickoff - b.nextKickoff) || (b.upcoming - a.upcoming),
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
  let storyCards: Awaited<ReturnType<typeof api.storylines>>["cards"] = []
  let storyWindow: "today" | "recent" = "today"
  try {
    const [p, s, st] = await Promise.all([
      api.tournament(),
      api.historyStats(),
      api.storylines().catch(() => ({ cards: [], window: "today" as const })),
    ])
    proj = p
    stats = s
    storyCards = st.cards
    storyWindow = st.window
  } catch {
    /* hero degrades gracefully */
  }

  const filtered = groupFilter !== "All" ? matches.filter((m) => m.group === groupFilter) : matches
  const valueCount = matches.filter((m) => m.prediction?.markets.some((mk) => mk.ev > 0.05)).length

  return (
    <>
      <TopBar
        title={`Group Stage · Matchday ${matchday}`}
        subtitle={`${matches.length} matches · ${valueCount} with value picks`}
        action={<NotificationBell />}
      />

      <div className="px-3 sm:px-6 py-4 sm:py-5">
        {(proj || stats) && (
          <div className="mb-5">
            <HomeHero proj={proj} stats={stats} />
          </div>
        )}

        <StorylinesStrip cards={storyCards} window={storyWindow} />

        {/* Top community quotes across all teams + upcoming matches, sourced
            from the daily team-news + match-briefs harvests. Hidden on
            cold-start when both JSONs are empty. */}
        <LoudestTakes />

        <div className="flex gap-2 mb-4">
          {MATCHDAYS.map((md) => (
            <Link
              key={md}
              href={`/?matchday=${md}${groupFilter !== "All" ? `&group=${groupFilter}` : ""}`}
              prefetch={false}
              // scroll={false}: don't jump to the top when switching matchdays
              // (Next.js default). User flag 2026-06-21 — "matchday 3 from mobile
              // scrolls me up which is annoying". Same applies to the group chips
              // below: changing filter shouldn't lose your scroll position.
              scroll={false}
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
              scroll={false}
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
