import { TopBar } from "@/components/layout/TopBar"
import { EVBadge } from "@/components/common/EVBadge"
import { api } from "@/lib/api"
import type { ValueOpportunity } from "@/lib/types"

const FILTERS = [
  { value: "All", label: "All markets" },
  { value: "home_win", label: "Team Win" },
  { value: "draw", label: "Draw" },
  { value: "away_win", label: "Team Win" },
  { value: "over_2_5", label: "Over 2.5" },
  { value: "btts", label: "Both Teams Score" },
]

const UNIQUE_FILTERS = [
  { value: "All", label: "All markets" },
  { value: "home_win", label: "Win" },
  { value: "draw", label: "Draw" },
  { value: "over_2_5", label: "Over 2.5" },
  { value: "btts", label: "Both Teams Score" },
]

function evPct(ev: number) {
  const sign = ev >= 0 ? "+" : ""
  return `${sign}${(ev * 100).toFixed(1)}%`
}

function probPct(p: number) {
  return `${(p * 100).toFixed(0)}%`
}

function OpportunityCard({ opp }: { opp: ValueOpportunity }) {
  const isHighValue = opp.ev > 0.08
  return (
    <div
      className={[
        "bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 hover:border-[#243050] transition-colors",
        isHighValue ? "border-l-[3px] border-l-green-500" : "",
      ].join(" ")}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[11px] text-slate-500 font-medium">
            <span className="inline-block bg-[#1a2033] rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide mr-1.5">
              Group {opp.group}
            </span>
            {opp.match_label}
          </p>
          <p className="text-[14px] font-bold text-white mt-0.5">{opp.label}</p>
          <div className="flex items-center gap-3 mt-1.5 flex-wrap">
            <span className="text-[11px] text-slate-400">
              Our estimate: <strong className="text-white">{probPct(opp.our_prob)}</strong>
            </span>
            <span className="text-[11px] text-slate-400">
              Odds: <strong className="text-white">{opp.bookmaker_odds.toFixed(2)}</strong>
            </span>
            {opp.kelly_pct > 0 && (
              <span className="text-[11px] text-slate-500">
                Quarter-Kelly: <strong className="text-slate-300">{opp.kelly_pct.toFixed(1)}% of bank</strong>
              </span>
            )}
          </div>
        </div>
        <div className="flex-shrink-0">
          <span
            className={[
              "inline-block rounded-md px-2 py-1 text-[12px] font-bold tabular-nums",
              opp.ev > 0.05 ? "bg-green-950 text-green-400" : "bg-[#1a2033] text-slate-400",
            ].join(" ")}
          >
            {evPct(opp.ev)} EV
          </span>
        </div>
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
  const filtered =
    market === "All"
      ? opps
      : opps.filter((o) => {
          if (market === "home_win") return o.market === "home_win"
          if (market === "draw") return o.market === "draw"
          if (market === "over_2_5") return o.market === "over_2_5"
          if (market === "btts") return o.market === "btts"
          return true
        })

  return (
    <>
      <TopBar
        title="Value Board"
        subtitle={
          opps.length > 0
            ? `${opps.length} positive-edge opportunities across all markets`
            : "All markets across upcoming fixtures"
        }
      />

      <div className="px-4 py-4">
        <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          <strong className="text-slate-200">EV (Expected Value)</strong> is the mathematical edge.
          If our model puts a team at 68% but the odds only imply 59%, that gap is your edge.
          Green means the market is offering better odds than our model says it should.
        </div>

        <div className="flex gap-1.5 mb-4 flex-wrap">
          {UNIQUE_FILTERS.map((f) => (
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
                ? "No value opportunities detected. This updates as predictions and odds are refreshed."
                : "No opportunities in this market filter."}
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            {filtered.map((opp, i) => (
              <OpportunityCard key={`${opp.match_id}-${opp.market}-${i}`} opp={opp} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
