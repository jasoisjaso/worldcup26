import { TopBar } from "@/components/layout/TopBar"
import { MatchCard } from "@/components/match/MatchCard"
import { api } from "@/lib/api"
import type { Match, MatchPrediction } from "@/lib/types"

async function getMatchesWithPredictions(matchday?: number): Promise<(Match & { prediction?: MatchPrediction })[]> {
  const matches = await api.matches(undefined, matchday)
  const predictions = await Promise.allSettled(
    matches.map((m) => api.prediction(m.id))
  )
  return matches.map((match, i) => ({
    ...match,
    prediction: predictions[i].status === "fulfilled" ? predictions[i].value : undefined,
  }))
}

const GROUPS = ["All", "A", "B", "C", "D", "E", "F", "G", "H", "I", "J", "K", "L"]

export default async function MatchesPage({
  searchParams,
}: {
  searchParams: { group?: string; matchday?: string }
}) {
  const matchday = searchParams.matchday ? parseInt(searchParams.matchday) : 1
  const matches = await getMatchesWithPredictions(matchday)

  const filtered = searchParams.group && searchParams.group !== "All"
    ? matches.filter((m) => m.group === searchParams.group)
    : matches

  const valueCount = matches.filter((m) =>
    m.prediction?.markets.some((mk) => mk.ev > 0.05)
  ).length

  return (
    <>
      <TopBar
        title={`Group Stage - Matchday ${matchday}`}
        subtitle={`${matches.length} matches · ${valueCount} with detected market edge`}
      />

      <div className="px-6 py-5">
        <div className="flex gap-2 mb-4">
          {[1, 2, 3].map((md) => (
            <a
              key={md}
              href={`/?matchday=${md}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[12px] font-semibold border transition-colors",
                matchday === md
                  ? "bg-blue-900/40 border-blue-700 text-blue-300"
                  : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Matchday {md}
            </a>
          ))}
        </div>

        <div className="flex flex-wrap gap-1.5 mb-5 items-center">
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mr-1">Group</span>
          {GROUPS.map((g) => (
            <a
              key={g}
              href={`/?group=${g}&matchday=${matchday}`}
              className={[
                "px-2.5 py-1 rounded-md text-[11px] font-semibold border transition-colors",
                (searchParams.group ?? "All") === g
                  ? "bg-blue-950 border-blue-700 text-blue-300"
                  : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {g}
            </a>
          ))}
        </div>

        <div>
          {filtered.map((match) => (
            <MatchCard key={match.id} match={match} prediction={match.prediction} />
          ))}
          {filtered.length === 0 && (
            <p className="text-slate-500 text-sm py-8 text-center">No matches found for this filter.</p>
          )}
        </div>
      </div>
    </>
  )
}
