import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { MatchCard } from "@/components/match/MatchCard"
import { HomeHero } from "@/components/home/HomeHero"
import { NextUpHero } from "@/components/home/NextUpHero"
import { RoundSnapshot } from "@/components/home/RoundSnapshot"
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
 * when the user arrives with no explicit `?round=`. Preference: the round whose
 * next-upcoming kickoff is soonest. If everything is complete, the latest round
 * we have fixtures for. If pre-tournament, group stage.
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

/**
 * Group match cards by Brisbane-local date (e.g. "Sunday 28 June"). 16 R32
 * fixtures spread across 6 days is too dense for one undifferentiated list —
 * a day heading sets up "what am I looking at" in a single glance.
 *
 * Brisbane is the explicit timezone because the owner is in Brisbane and most
 * users are AU. Same rule as reference_au_timezone_skill: always pass an IANA
 * timeZone string on every server-rendered toLocale* call.
 */
function groupMatchesByDay(
  matches: (Match & { prediction?: MatchPrediction })[],
): { day: string; matches: (Match & { prediction?: MatchPrediction })[] }[] {
  const buckets: Record<string, (Match & { prediction?: MatchPrediction })[]> = {}
  const order: string[] = []
  for (const m of matches) {
    const day = new Date(m.kickoff).toLocaleDateString("en-AU", {
      weekday: "long",
      day: "numeric",
      month: "long",
      timeZone: "Australia/Brisbane",
    })
    if (!buckets[day]) {
      buckets[day] = []
      order.push(day)
    }
    buckets[day].push(m)
  }
  return order.map((day) => ({ day, matches: buckets[day] }))
}

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: { group?: string; matchday?: string; round?: string }
}) {
  const explicitRound = sanitiseRound(searchParams.round)
  const explicitMd = sanitiseGroupMatchday(searchParams.matchday)
  const groupFilter = sanitiseGroup(searchParams.group)

  let activeRoundKey: RoundKey
  let activeGroupMd: GroupMatchday = 3
  let matches: (Match & { prediction?: MatchPrediction })[]

  if (explicitRound) {
    activeRoundKey = explicitRound
    if (activeRoundKey === "group") {
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
    activeRoundKey = "group"
    activeGroupMd = explicitMd
    matches = await getMatchesWithPredictions([activeGroupMd])
  } else {
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
  const isKnockout = activeRoundKey !== "group"
  const showGroupFilter = !isKnockout

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

  if (isKnockout) {
    filtered.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())
  }

  const valueCount = matches.filter((m) =>
    m.prediction?.markets.some((mk) => mk.ev > 0.05),
  ).length

  const topBarTitle = showGroupFilter
    ? `Group Stage · Matchday ${activeGroupMd}`
    : activeRound.label
  const topBarSubtitle = `${matches.length} matches · ${valueCount} with value picks`

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

  const grouped = isKnockout ? groupMatchesByDay(filtered) : null

  return (
    <>
      <TopBar title={topBarTitle} subtitle={topBarSubtitle} action={<NotificationBell />} />

      <div className="px-3 sm:px-6 py-4 sm:py-5">
        {/* Hero: knockout rounds lead with "next match + countdown + top pick";
            group stage stays with the trophy-contenders hero. */}
        {isKnockout ? (
          <div className="mb-5">
            <NextUpHero matches={matches} roundLabel={activeRound.label} />
          </div>
        ) : (
          (proj || stats) && (
            <div className="mb-5">
              <HomeHero proj={proj} stats={stats} />
            </div>
          )
        )}

        {/* Knockout: live round stats banner. Group stage: drama cards strip. */}
        {isKnockout ? (
          <RoundSnapshot matches={matches} roundLabel={activeRound.label} />
        ) : (
          <StorylinesStrip cards={storyCards} window={storyWindow} />
        )}

        <LoudestTakes />

        {/* Round tabs. */}
        <div className="flex gap-2 mb-4 overflow-x-auto pb-1 -mx-1 px-1">
          {ROUNDS.map((r) => (
            <Link
              key={r.key}
              href={hrefForRound(r.key)}
              prefetch={false}
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

        {/* Match cards. KO rounds get date headings to break up six days of
            fixtures; group stage stays as a flat list. */}
        <div>
          {grouped ? (
            grouped.map(({ day, matches: dayMatches }) => (
              <div key={day} className="mb-1">
                <div className="flex items-baseline gap-2 mt-5 mb-2 pb-1.5 border-b border-edge">
                  <h3 className="text-[12px] font-black uppercase tracking-[0.15em] text-emerald-300">
                    {day}
                  </h3>
                  <span className="text-[10px] font-bold text-slate-600 tabular-nums">
                    {dayMatches.length} {dayMatches.length === 1 ? "match" : "matches"}
                  </span>
                </div>
                {dayMatches.map((match) => (
                  <MatchCard
                    key={match.id}
                    match={match}
                    prediction={match.prediction}
                    from="/"
                  />
                ))}
              </div>
            ))
          ) : (
            filtered.map((match) => (
              <MatchCard key={match.id} match={match} prediction={match.prediction} from="/" />
            ))
          )}
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
