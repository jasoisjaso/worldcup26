import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { AccaCombo } from "@/lib/types"

function evPct(ev: number) {
  const sign = ev >= 0 ? "+" : ""
  return `${sign}${(ev * 100).toFixed(1)}%`
}

function probPct(p: number) {
  return `${(p * 100).toFixed(1)}%`
}

function ComboCard({ combo, legs }: { combo: AccaCombo; legs: number }) {
  return (
    <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl overflow-hidden mb-3">
      <div className="px-4 py-3 border-b border-[#1a2033] flex items-center justify-between">
        <div>
          <span className="text-[13px] font-bold text-white">{legs}-Leg Acca</span>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Combined odds: <strong className="text-slate-300">{combo.combined_odds.toFixed(2)}</strong>
            <span className="mx-2 text-[#1a2033]">|</span>
            Probability: <strong className="text-slate-300">{probPct(combo.combined_probability)}</strong>
          </p>
        </div>
        <span
          className={[
            "rounded-md px-2.5 py-1 text-[13px] font-bold tabular-nums",
            combo.ev > 0 ? "bg-green-950 text-green-400" : "bg-[#1a2033] text-slate-400",
          ].join(" ")}
        >
          {evPct(combo.ev)} EV
        </span>
      </div>

      <div className="divide-y divide-[#1a2033]">
        {combo.legs.map((leg, i) => (
          <div key={i} className="px-4 py-2.5 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-[12px] font-semibold text-white truncate">{leg.label}</p>
              <p className="text-[11px] text-slate-500 truncate">
                <span className="inline-block bg-[#1a2033] rounded px-1 mr-1 text-[9px] font-bold uppercase tracking-wide">
                  {leg.group}
                </span>
                {leg.match_label}
              </p>
            </div>
            <div className="flex-shrink-0 text-right">
              <p className="text-[12px] font-bold text-slate-300">{leg.bookmaker_odds.toFixed(2)}</p>
              <p className="text-[10px] text-green-500 font-semibold">{evPct(leg.ev)}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default async function AccaPage({
  searchParams,
}: {
  searchParams: { k?: string }
}) {
  const k = Math.min(5, Math.max(3, parseInt(searchParams.k ?? "5")))
  let combos: AccaCombo[] = []
  try {
    combos = await api.acca(k)
  } catch {
    combos = []
  }

  return (
    <>
      <TopBar
        title="Acca Builder"
        subtitle="Best accumulator combinations by total expected value"
      />

      <div className="px-4 py-4">
        <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          An <strong className="text-slate-200">accumulator</strong> combines multiple match
          bets into one. All legs must win for you to get paid. These combinations are chosen
          because each leg has a positive mathematical edge, not just the longest odds.
          <span className="block mt-1 text-slate-500">
            Quarter-Kelly staking guide: use the per-leg kelly percentages from the Value Board
            as a sizing guide. Stake less, not more, on accas.
          </span>
        </div>

        <div className="flex gap-1.5 mb-4">
          {[3, 4, 5].map((n) => (
            <a
              key={n}
              href={`/acca?k=${n}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                k === n
                  ? "bg-blue-900/40 border-blue-700 text-blue-300"
                  : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Up to {n} legs
            </a>
          ))}
        </div>

        {combos.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-500 text-[14px]">
              Not enough positive-EV legs found yet to build a {k}-leg combination.
              Check back once more matches have odds data.
            </p>
          </div>
        ) : (
          <div>
            {combos.map((combo, i) => (
              <ComboCard key={i} combo={combo} legs={combo.legs.length} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
