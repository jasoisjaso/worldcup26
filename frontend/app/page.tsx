import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { MatchCard } from "@/components/match/MatchCard"
import { HomeHero } from "@/components/home/HomeHero"
import { StorylinesStrip } from "@/components/home/StorylinesStrip"
import { LoudestTakes } from "@/components/home/LoudestTakes"
import { NotificationBell } from "@/components/common/NotificationBell"
import { api } from "@/lib/api"
import { ROUNDS, ROUND_BY_KEY, roundForMatchday, type RoundKey } from "@/lib/rounds"
import type { Match, MatchPrediction, TournamentProjection, HistoryStats } from "@/lib/types"

const GROUPS = ["All", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]
const GROUP_MATCHDAYS = [1, 2, 3] as const
type GroupMatchday = (typeof GROUP_MATCHDAYS)[number]

/**
 * Pick the round (Group / R32 / R16 / QF / SF / Final) the page should land on
 * when the user arrives with no explicit `?round=`. We want them to see what's
 * happening NEXT — preference order:
 *
 *   1. The round whose next-upcoming kickoff is soonest. Ties broken by the
 *      round with more upcoming matches.
 *   2. If every match in every round is complete, the latest round we have
 *      fixtures for (so the tournament-over landing page is the final, not
 *      matchday 1).
 *   3. Otherwise — pre-tournament with no data — the group stage.
 */
function pickActiveRound(matches: Match[], now = Date.now()): RoundKey {
  if (matches.length === 0) return "group"

  const buckets = ROUNDS.map((r) => ({
    key: r.key,
    upcoming: 0,
    nextKickoff: Infinity,
    anyKnown: false,
  }))

  let anyUpcoming = false
  for (const m of matches) {
    const r = roundForMatchday(m.matchday)
    const b = buckets.find((x) => x.key === r.key)
    if (!b) continue
    b.anyKnown = true
    const ko = new Date(m.kickoff).getTime()
    if (m.status !== "complete" && ko > now) {
      b.upcoming += 1
      b.nextKickoff = Math.min(b.nextKickoff, ko)
      anyUpcoming = true
    }
  }

  if (anyUpcoming) {
    return [...buckets].sort(
      (a, b) => (a.nextKickoff - b.nextKickoff) || (b.upcoming - a.upcoming),
    )[0].key
  }
  for (let i = buckets.length - 1; i >= 0; i--) {
    if (buckets[i].anyKnown) return buckets[i].key
  }
  return "group"
}

/** Within the Group Stage tab, pick the soonest-active matchday (or MD3 if all done). */
function pickActiveGroupMatchday(matches: Match[], now = Date.now()): GroupMatchday {
  const buckets: { md: GroupMatchday; upcoming: number; nextKickoff: number }[] =
    GROUP_MATCHDAYS.map((md) => ({ md, upcoming: 0, nextKickoff: Infinity }))
  let any = false
  for (const m of matches) {
    if (!(GROUP_MATCHDAYS as readonly number[]).includes(m.matchday)) continue
    const b = buckets.find((x) => x.md === m.matchday)
    if (!b) continue
    const ko = new Date(m.kickoff).getTime()
    if (m.status !== "complete" && ko > now) {
      b.upcoming += 1
      b.nextKickoff = Math.min(b.nextKickoff, ko)
      any = true
    }
  }
  if (any) {
    return [...buckets].sort(
      (a, b) => (a.nextKickoff - b.nextKickoff) || (b.upcoming - a.upcoming),
    )[0].md
  }
  return 3
}

function sanitiseGroup(raw: string | undefined): string {
  return raw && GROUPS.includes(raw) ? raw : "All"
}

function sanitiseRound(raw: string | undefined): RoundKey | null {
  if (!raw) return null
  return raw in ROUND_BY_KEY ? (raw as RoundKey) : null
}

function sanitiseGroupMatchday(raw: string | undefined): GroupMatchday | null {
  const n = raw ? Number.parseInt(raw, 10) : NaN
  return Number.isFinite(n) && (GROUP_MATCHDAYS as readonly number[]).includes(n)
    ? (n as GroupMatchday)
    : null
}

async function getMatchesWithPredictions(
  matchdays: number[],
): Promise<(Match & { prediction?: MatchPrediction })[]> {
  const buckets = await Promise.all(matchdays.map((md) => api.matches(undefined, md)))
  const matches = buckets.flat()
  const predictions = await Promise.allSettled(matches.map((m) => api.prediction(m.id)))
  return matches.map((match, i) => ({
    ...match,
    prediction: predictions[i].status === "fulfilled" ? predictions[i].value : undefined,
  }))
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: { group?: string; matchday?: string; round?: string }
}) {
  // Round resolution. New URL: ?round=r32. Legacy: ?matchday=4 → derive round.
  const explicitRound = sanitiseRound(searchParams.round)
  const explicitMd = sanitiseGroupMatchday(searchParams.matchday)
  const groupFilter = sanitiseGroup(searchParams.group)

  let activeRoundKey: RoundKey
  let activeGroupMd: GroupMatchday = 3
  let matches: (Match & { prediction?: MatchPrediction })[]

  if (explicitRound) {
    activeRoundKey = explicitRound
    if (activeRoundKey === "group") {
      // Group stage with optional sub-matchday selection.
      if (explicitMd) {
        activeGroupMd = explicitMd
        matches = await getMatchesWithPredictions([activeGroupMd])
      } else {
        const all = await api.matches()
        activeGroupMd = pickActiveGroupMatchday(all)
        matches = await getMatchesWithPredictions([activeGroupMd])
      }
    } else {
      matches = await getMatchesWithPredictions(ROUND_BY_KEY[activeRoundKey].matchdays)
    }
  } else if (explicitMd) {
    // Legacy direct ?matchday=N — only valid for group stage.
    activeRoundKey = "group"
    activeGroupMd = explicitMd
    matches = await getMatchesWithPredictions([activeGroupMd])
  } else {
    // No explicit selection — pick the round with the soonest next kickoff.
    const all = await api.matches()
    activeRoundKey = pickActiveRound(all)
    if (activeRoundKey === "group") {
      activeGroupMd = pickActiveGroupMatchday(all)
      matches = await getMatchesWithPredictions([activeGroupMd])
    } else {
      matches = await getMatchesWithPredictions(ROUND_BY_KEY[activeRoundKey].matchdays)
    }
  }

  const activeRound = ROUND_BY_KEY[activeRoundKey]
  const showGroupFilter = activeRoundKey === "group"

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

  const filtered =
    showGroupFilter && groupFilter !== "All"
      ? matches.filter((m) => m.group === groupFilter)
      : matches

  // Sort knockout matches chronologically so the page reads top-to-bottom by kickoff.
  if (!showGroupFilter) {
    filtered.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())
  }

  const valueCount = matches.filter((m) =>
    m.prediction?.markets.some((mk) => mk.ev > 0.05),
  ).length

  const topBarTitle = showGroupFilter
    ? `Group Stage · Matchday ${activeGroupMd}`
    : activeRound.label
  const topBarSubtitle = `${matches.length} matches · ${valueCount} with value picks`

  // URL helpers — preserve group filter where it makes sense.
  const hrefForRound = (key: RoundKey): string => {
    if (key === "group") {
      const qs = new URLSearchParams({ round: "group" })
      if (groupFilter !== "All") qs.set("group", groupFilter)
      return `/?${qs.toString()}`
    }
    return `/?round=${key}`
  }
  const hrefForGroupMatchday = (md: GroupMatchday): string => {
    const qs = new URLSearchParams({ round: "group", matchday: String(md) })
    if (groupFilter !== "All") qs.set("group", groupFilter)
    return `/?${qs.toString()}`
  }
  const hrefForGroup = (g: string): string => {
    const qs = new URLSearchParams({ round: "group", matchday: String(activeGroupMd) })
    if (g !== "All") qs.set("group", g)
    return `/?${qs.toString()}`
  }

  return (
    <>
      <TopBar title={topBarTitle} subtitle={topBarSubtitle} action={<NotificationBell />} />

      <div className="px-3 sm:px-6 py-4 sm:py-5">
        {(proj || stats) && (
          <div className="mb-5">
            <HomeHero proj={proj} stats={stats} />
          </div>
        )}

        <StorylinesStrip cards={storyCards} window={storyWindow} />

        <LoudestTakes />

        {/* Round tabs. Replaces the old Matchday 1/2/3 pills now that the
            tournament has moved beyond the group stage. Scrolls horizontally
            on mobile so the six labels fit without truncation. */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1 -mx-1 px-1">
          {ROUNDS.map((r) => (
            <Link
              key={r.key}
              href={hrefForRound(r.key)}
              prefetch={false}
              // scroll={false}: switching rounds shouldn't jump the user back to
              // the top — they often switch round to compare the same area of
              // the page.
              scroll={false}
              className={[
                "shrink-0 px-3 py-1.5 rounded-lg text-[12px] font-semibold border transition-colors whitespace-nowrap",
                activeRoundKey === r.key
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {r.label}
            </Link>
          ))}
        </div>

        {/* Group-stage-only: matchday sub-pills + A-L group filter. */}
        {showGroupFilter && (
          <>
            <div className="flex gap-2 mb-4">
              {GROUP_MATCHDAYS.map((md) => (
                <Link
                  key={md}
                  href={hrefForGroupMatchday(md)}
                  prefetch={false}
                  scroll={false}
                  className={[
                    "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                    activeGroupMd === md
                      ? "bg-emerald-950 border-emerald-800 text-emerald-300"
                      : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
                  ].join(" ")}
                >
                  Matchday {md}
                </Link>
              ))}
            </div>

            <div className="flex flex-wrap gap-1.5 mb-5 items-center">
              <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mr-1">
                Group
              </span>
              {GROUPS.map((g) => (
                <Link
                  key={g}
                  href={hrefForGroup(g)}
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
          </>
        )}

        {/* Knockout-round context banner: light orientation so users coming
            from the old "Matchday X" layout know what they're looking at. */}
        {!showGroupFilter && (
          <div className="mb-4 px-3 py-2.5 rounded-lg border border-edge bg-surface-2/40 text-[12px] text-slate-400 leading-snug">
            <span className="font-bold text-slate-300">{activeRound.label}</span>
            {" · "}
            single-elimination. Tied at 90 minutes go to extra time, then penalties.
          </div>
        )}

        <div>
          {filtered.map((match) => (
            <MatchCard key={match.id} match={match} prediction={match.prediction} from="/" />
          ))}
          {filtered.length === 0 && (
            <p className="text-slate-500 text-sm py-8 text-center">
              No matches found for this filter.
            </p>
          )}
        </div>
      </div>
    </>
  )
}
