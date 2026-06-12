import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { ValueOpportunity } from "@/lib/types"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Value Board",
  description: "Live value bets for 2026 FIFA World Cup matches. Our ELO model vs bookmaker odds across all group stage games.",
}

const MARKET_FILTERS = [
  { value: "All", label: "All" },
  { value: "home_win", label: "Home Win" },
  { value: "draw", label: "Draw" },
  { value: "away_win", label: "Away Win" },
  { value: "over_2_5", label: "Over 2.5" },
  { value: "btts", label: "BTTS" },
]

const MATCHDAY_FILTERS = [
  { value: "All", label: "All" },
  { value: "1", label: "MD 1" },
  { value: "2", label: "MD 2" },
  { value: "3", label: "MD 3" },
]

function reliabilityRating(reliability?: string): { stars: number; label: string; color: string } {
  // Trust is based on how far the model strays from a sharp market — NOT raw EV, which
  // rewards longshots where the model is most likely just wrong.
  if (reliability === "solid") return { stars: 3, label: "Solid edge", color: "text-green-400" }
  if (reliability === "speculative") return { stars: 2, label: "Speculative", color: "text-yellow-400" }
  return { stars: 1, label: "Longshot · market disagrees", color: "text-slate-500" }
}

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

function TabLink({
  href,
  active,
  label,
}: {
  href: string
  active: boolean
  label: string
}) {
  return (
    <a
      href={href}
      className={[
        "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
        active
          ? "bg-blue-900/40 border-blue-700 text-blue-300"
          : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
      ].join(" ")}
    >
      {label}
    </a>
  )
}


function OpportunityCard({ opp }: { opp: ValueOpportunity }) {
  const marketOddsImplied = Math.round((1 / opp.bookmaker_odds) * 100)
  // The edge is our model's OWN opinion vs the bookie line — not the market-blended
  // display number, which would shrink the gap toward the bookie.
  const modelPct = Math.round((opp.model_prob ?? opp.our_prob) * 100)
  const calibratedPct = Math.round(opp.our_prob * 100)
  const gapPct = modelPct - marketOddsImplied
  const { stars, label, color } = reliabilityRating(opp.reliability)
  const isLongshot = opp.reliability === "longshot"
  const { stake, returns, profit } = betExample(opp.bookmaker_odds)

  return (
    <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-4 hover:border-[#243050] transition-colors">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="min-w-0">
          <p className="text-[10px] text-slate-600 font-bold mb-1">
            <span className="uppercase tracking-widest">MD{opp.matchday} · Group {opp.group}</span>
            <span className="normal-case"> · {opp.match_label}</span>
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

      <div className="bg-[#080c14] rounded-lg px-3 py-2.5 mb-3 space-y-1">
        <div className="flex justify-between text-[11px]">
          <span className="text-slate-500">Bookie's odds imply</span>
          <span className="text-slate-300 font-semibold">{marketOddsImplied}% chance</span>
        </div>
        <div className="flex justify-between text-[11px]">
          <span className="text-slate-500">Our model rates it</span>
          <span className="text-white font-bold">{modelPct}% chance</span>
        </div>
        <div className="flex justify-between text-[11px] border-t border-[#1a2033] pt-1 mt-1">
          <span className="text-slate-500">Our edge over the book</span>
          <span className={`font-bold ${gapPct > 0 ? "text-green-400" : "text-red-400"}`}>
            {gapPct > 0 ? "+" : ""}{gapPct} pts
          </span>
        </div>
        <p className="text-[9.5px] text-slate-600 pt-0.5">
          Calibrated estimate (model sanity-checked against the market): {calibratedPct}%
        </p>
      </div>

      {isLongshot && (
        <div className="bg-amber-950/30 border border-amber-800/40 rounded-lg px-3 py-2 mb-3">
          <p className="text-[10.5px] text-amber-400/90 leading-snug">
            ⚠ High-risk: our model rates this well above the bookie, but a sharp market rarely
            misprices by this much. Treat it as a long shot, not a sure thing.
          </p>
        </div>
      )}

      <p className="text-[11px] text-slate-500">
        Example: <span className="text-slate-300">${stake} bet</span>
        {" → "}
        <span className="text-green-400 font-semibold">+${profit} profit</span>
        <span className="text-slate-600"> (${returns} returned) if correct</span>
      </p>
    </div>
  )
}

export default async function ValuePage({
  searchParams,
}: {
  searchParams: { market?: string; md?: string }
}) {
  let opps: ValueOpportunity[] = []
  try {
    opps = await api.value()
  } catch {
    opps = []
  }

  const market = searchParams.market ?? "All"
  const md = searchParams.md ?? "All"
  const MAX_SHOWN = 20

  const allFiltered = opps
    .filter((o) => market === "All" || o.market === market)
    .filter((o) => md === "All" || String(o.matchday) === md)
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
            ? `Top ${filtered.length} of ${allFiltered.length} picks where our model sees an edge`
            : "No value detected right now"
        }
      />

      <div className="px-4 py-4">
        <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          Bets where our model thinks the bookie is underestimating a team. Odds above 10.0 excluded.
          <span className="text-slate-300"> Three stars = strong gap between model and market price.</span>
          {" "}Odds are the median across Bet365, Sportsbet, and Unibet. Your bookmaker may offer slightly different prices.
        </div>

        {topPick && (
          <div className="bg-green-950/30 border border-green-800/40 rounded-xl px-4 py-3 mb-4">
            <p className="text-[10px] text-green-600 uppercase tracking-widest font-bold mb-1">Top pick right now</p>
            <p className="text-[14px] font-bold text-white">{topPick.label}</p>
            <p className="text-[12px] text-slate-400 mt-0.5">
              {topPick.match_label} · MD{topPick.matchday} ·{" "}
              <span className="text-white font-bold">@{topPick.bookmaker_odds.toFixed(2)}</span>
              {" · "}our model: {Math.round((topPick.model_prob ?? topPick.our_prob) * 100)}% vs bookie implies: {Math.round((1 / topPick.bookmaker_odds) * 100)}%
            </p>
          </div>
        )}

        {/* Matchday tabs */}
        <div className="mb-3">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">Matchday</p>
          <div className="flex gap-1.5 flex-wrap">
            {MATCHDAY_FILTERS.map((f) => (
              <TabLink
                key={f.value}
                href={`/value?md=${f.value}&market=${market}`}
                active={md === f.value}
                label={f.label}
              />
            ))}
          </div>
        </div>

        {/* Market tabs */}
        <div className="mb-4">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">Market</p>
          <div className="flex gap-1.5 flex-wrap">
            {MARKET_FILTERS.map((f) => (
              <TabLink
                key={f.value}
                href={`/value?md=${md}&market=${f.value}`}
                active={market === f.value}
                label={f.label}
              />
            ))}
          </div>
        </div>

        {filtered.length === 0 ? (
          <div className="text-center py-12 px-6">
            {opps.length === 0 ? (
              <>
                <p className="text-slate-400 text-[14px] font-semibold mb-1">No live value right now</p>
                <p className="text-slate-500 text-[12px] leading-relaxed max-w-sm mx-auto">
                  Value picks appear when the model finds a gap against live bookmaker odds.
                  The odds feed is quiet at the moment — meanwhile every match has a full model
                  prediction on the{" "}
                  <a href="/" className="text-blue-400 font-semibold hover:underline">Matches page</a>.
                </p>
              </>
            ) : (
              <p className="text-slate-500 text-[14px]">No opportunities in this filter.</p>
            )}
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
