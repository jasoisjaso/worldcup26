import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { ValueOpportunity } from "@/lib/types"

const FILTERS = [
  { value: "All", label: "All" },
  { value: "home_win", label: "Win" },
  { value: "draw", label: "Draw" },
  { value: "over_2_5", label: "Over 2.5" },
  { value: "btts", label: "BTTS" },
]

// Stars: how strong the edge is relative to stake
function edgeStars(ev: number): { stars: number; label: string; color: string } {
  if (ev >= 0.25) return { stars: 3, label: "Strong edge", color: "text-green-400" }
  if (ev >= 0.10) return { stars: 2, label: "Decent edge", color: "text-yellow-400" }
  return { stars: 1, label: "Marginal edge", color: "text-slate-400" }
}

// Plain-English bet example for a $50 stake
function betExample(odds: number) {
  const stake = 50
  const returns = (stake * odds).toFixed(0)
  const profit = (stake * odds - stake).toFixed(0)
  return { stake, returns, profit }
}

function Stars({ count }: { count: number }) {
  return (
    <span className="text-yellow-400 text-[13px] tracking-tight">
      {"★".repeat(count)}{"☆".repeat(3 - count)}
    </span>
  )
}

function OpportunityCard({ opp }: { opp: ValueOpportunity }) {
  const marketOddsImplied = Math.round((1 / opp.bookmaker_odds) * 100)
  const ourPct = Math.round(opp.our_prob * 100)
  const gapPct = ourPct - marketOddsImplied
  const { stars, label, color } = edgeStars(opp.ev)
  const { stake, returns, profit } = betExample(opp.bookmaker_odds)

  return (
    <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-4 hover:border-[#243050] transition-colors">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <p className="text-[10px] text-slate-600 uppercase tracking-widest font-bold mb-1">
            Group {opp.group} · {opp.match_label}
          </p>
          <p className="text-[15px] font-bold text-white leading-tight">{opp.label}</p>
          <p className="text-[12px] text-slate-400 mt-0.5">
            @ <span className="text-white font-bold">{opp.bookmaker_odds.toFixed(2)}</span>
          </p>
        </div>
        <div className="flex-shrink-0 text-right">
          <Stars count={stars} />
          <p className={`text-[11px] font-semibold mt-0.5 ${color}`}>{label}</p>
        </div>
      </div>

      {/* Plain-English breakdown */}
      <div className="bg-[#080c14] rounded-lg px-3 py-2.5 mb-3 space-y-1">
        <div className="flex justify-between text-[11px]">
          <span className="text-slate-500">Bookie implies</span>
          <span className="text-slate-300 font-semibold">{marketOddsImplied}% chance</span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-slate-500">Our model says</span>
          <span className="text-white font-bold">{ourPct}% chance</span>
        </div>
        <div className="flex justify-between text-[11px] border-t border-[#1a2033] pt-1 mt-1">
          <span className="text-slate-500">Edge (our estimate vs market)</span>
          <span className={`font-bold ${gapPct > 0 ? "text-green-400" : "text-red-400"}`}>
            +{gapPct} pts
          </span>
        </div>
      </div>

      {/* Bet example */}
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-slate-500">
          Example: <span className="text-slate-300">${stake} bet</span>
          {" → "}
          <span className="text-green-400 font-semibold">+${profit} profit</span>
          <span className="text-slate-600"> (${returns} returned) if correct</span>
        </p>
        {opp.kelly_pct > 0 && (
          <span className="text-[10px] text-slate-600 flex-shrink-0 ml-2">
            Kelly: {opp.kelly_pct.toFixed(1)}% of bank
          </span>
        )}
      </div>
    </div>
  )
}

export default async function ValuePage({
  searchParams,
}: {
  searchParams: { market?: string }
}) {
  let opps: ValueOpportunity[] = []
  try {
    opps = await api.value()
  } catch {
    opps = []
  }

  const market = searchParams.market ?? "All"
  const MAX_SHOWN = 20
  const allFiltered = (
    market === "All"
      ? opps
      : opps.filter((o) => o.market === market)
  )
    .filter((o) => o.ev >= 0.10 && o.ev <= 1.5 && o.bookmaker_odds <= 10.0)
    .sort((a, b) => b.ev - a.ev)
  const filtered = allFiltered.slice(0, MAX_SHOWN)

  const topPick = filtered[0]

  return (
    <>
      <TopBar
        title="Value Board"
        subtitle={
          allFiltered.length > 0
            ? `Top ${filtered.length} picks of ${allFiltered.length} where our model sees an edge`
            : "No value detected right now"
        }
      />

      <div className="px-4 py-4">
        {/* What this page does */}
        <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          Bets where our model thinks the bookie is underestimating a team. Odds above 10.0 are excluded.
          <span className="text-slate-300"> Three stars = strong gap between our estimate and the market price.</span>
          {" "}Sorted by edge size. Top 20 shown.
        </div>

        {/* Best pick callout */}
        {topPick && (
          <div className="bg-green-950/30 border border-green-800/40 rounded-xl px-4 py-3 mb-4">
            <p className="text-[10px] text-green-600 uppercase tracking-widest font-bold mb-1">Top pick right now</p>
            <p className="text-[14px] font-bold text-white">{topPick.label}</p>
            <p className="text-[12px] text-slate-400 mt-0.5">
              {topPick.match_label} ·{" "}
              <span className="text-white font-bold">@{topPick.bookmaker_odds.toFixed(2)}</span>
              {" · "}our model: {Math.round(topPick.our_prob * 100)}% vs market: {Math.round((1 / topPick.bookmaker_odds) * 100)}%
            </p>
          </div>
        )}

        {/* Market filter tabs */}
        <div className="flex gap-1.5 mb-4 flex-wrap">
          {FILTERS.map((f) => (
            <a
              key={f.value}
              href={`/value?market=${f.value}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                market === f.value
                  ? "bg-blue-900/40 border-blue-700 text-blue-300"
                  : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {f.label}
            </a>
          ))}
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-500 text-[14px]">
              {opps.length === 0
                ? "No value opportunities detected. Updates every 4 hours."
                : "No opportunities in this market filter."}
            </p>
          </div>
        ) : (
          <div className="space-y-3">
            {filtered.map((opp, i) => (
              <OpportunityCard key={`${opp.match_id}-${opp.market}-${i}`} opp={opp} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
