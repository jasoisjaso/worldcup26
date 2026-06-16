import type { Metadata } from "next"
import Link from "next/link"
import { ChevronLeft } from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { MarketsSheet } from "@/components/match/MarketsSheet"
import { KickoffTime } from "@/components/common/KickoffTime"
import { api } from "@/lib/api"
import type { Match, MatchPrediction, MarketsSheet as Sheet } from "@/lib/types"

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  try {
    const m = await api.match(params.id)
    const title = `${m.home.name} vs ${m.away.name}: Prediction & Fair Odds`
    return {
      title,
      description: `Model prediction, win probabilities and fair odds across 30+ betting markets for ${m.home.name} vs ${m.away.name} at the 2026 World Cup.`,
      alternates: { canonical: `https://wc26.tinjak.com/match/${params.id}` },
    }
  } catch {
    return { title: "Match prediction" }
  }
}

function Flag({ url, color, size = "w-9 h-[26px]" }: { url?: string; color?: string; size?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${size} rounded object-cover ring-1 ring-white/10 mx-auto`} />
  }
  return <span className={`${size} rounded ring-1 ring-white/10 mx-auto block`} style={{ background: color || "#1e293b" }} />
}

export default async function MatchPage({ params }: { params: { id: string } }) {
  let match: Match | null = null
  let prediction: MatchPrediction | null = null
  let sheet: Sheet | null = null
  try {
    ;[match, prediction, sheet] = await Promise.all([
      api.match(params.id),
      api.prediction(params.id).catch(() => null),
      api.markets(params.id).catch(() => null),
    ])
  } catch {
    /* match not found */
  }

  if (!match) {
    return (
      <>
        <TopBar title="Match" />
        <p className="text-slate-500 text-sm py-16 text-center px-4">Match not found.</p>
      </>
    )
  }

  const complete = match.status === "complete" && match.actual_score != null

  return (
    <>
      <TopBar title={`${match.home.name} vs ${match.away.name}`} subtitle={`Group ${match.group} · Matchday ${match.matchday}`} />

      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">
        <Link href="/" className="inline-flex items-center gap-1 text-[12px] text-slate-500 hover:text-slate-300 mb-4">
          <ChevronLeft size={14} /> All matches
        </Link>

        {/* header */}
        <div className="rounded-2xl border border-[#16203a] bg-[#0b1018] p-5 mb-5">
          <p className="text-[11px] text-slate-500 text-center mb-3">
            <KickoffTime iso={match.kickoff} /> · {match.venue}
          </p>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div className="text-center">
              <Flag url={match.home.flag_url} color={match.home.primary_color} />
              <p className="text-[14px] font-bold text-slate-100 mt-2">{match.home.name}</p>
              {prediction && <p className="text-[26px] font-black text-emerald-400 tabular-nums leading-none mt-1">{Math.round(prediction.home_win * 100)}%</p>}
            </div>
            <div className="text-center px-2">
              {complete ? (
                <>
                  <p className="text-[9px] text-slate-600 font-bold uppercase tracking-widest">FT</p>
                  <p className="text-[24px] font-black text-white tabular-nums">{match.actual_score!.home}&ndash;{match.actual_score!.away}</p>
                </>
              ) : (
                <>
                  <p className="text-[10px] text-slate-700 font-bold tracking-widest">VS</p>
                  {prediction && (
                    <>
                      <p className="text-[15px] font-bold text-slate-400 tabular-nums mt-1">{Math.round(prediction.draw * 100)}%</p>
                      <p className="text-[8px] text-slate-700 uppercase tracking-wide">draw</p>
                    </>
                  )}
                </>
              )}
            </div>
            <div className="text-center">
              <Flag url={match.away.flag_url} color={match.away.primary_color} />
              <p className="text-[14px] font-bold text-slate-100 mt-2">{match.away.name}</p>
              {prediction && <p className="text-[26px] font-black text-orange-400 tabular-nums leading-none mt-1">{Math.round(prediction.away_win * 100)}%</p>}
            </div>
          </div>

          {prediction && (
            <div className="mt-4 flex h-2 rounded-full overflow-hidden bg-[#0a0f18]">
              <div className="bg-emerald-500" style={{ width: `${prediction.home_win * 100}%` }} />
              <div className="bg-slate-600" style={{ width: `${prediction.draw * 100}%` }} />
              <div className="bg-orange-500" style={{ width: `${prediction.away_win * 100}%` }} />
            </div>
          )}
        </div>

        {/* why factors */}
        {prediction && prediction.why_factors.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Why the model leans this way</p>
            <div className="flex flex-wrap gap-1.5">
              {prediction.why_factors.map((f, i) => (
                <span
                  key={i}
                  className={[
                    "text-[11px] px-2.5 py-1 rounded-md border",
                    f.direction === "positive" ? "border-emerald-900/60 bg-emerald-950/30 text-emerald-300"
                      : f.direction === "negative" ? "border-rose-900/60 bg-rose-950/30 text-rose-300"
                      : "border-[#1a2233] bg-[#0f1320] text-slate-400",
                  ].join(" ")}
                >
                  {f.label}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* markets sheet */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Fair odds for every market</p>
        {sheet ? (
          <MarketsSheet sheet={sheet} />
        ) : (
          <p className="text-[12px] text-slate-600">Markets unavailable for this match right now.</p>
        )}
      </div>
    </>
  )
}
