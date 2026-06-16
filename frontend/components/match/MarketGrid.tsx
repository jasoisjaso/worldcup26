import { Tooltip } from "@/components/common/Tooltip"
import { formatPercent, formatOdds, formatEV, evColor } from "@/lib/utils"
import type { Market } from "@/lib/types"

const JARGON: Record<string, string> = {
  over_2_5: "Over 2.5 Goals: this match finishes with 3 or more total goals.",
  btts: "Both Teams Score: both sides get on the scoresheet regardless of the final result.",
  ah_home_minus1: "Asian Handicap -1.0: the stronger team must win by 2 or more goals. Removes the draw.",
}

interface MarketGridProps {
  markets: Market[]
}

export function MarketGrid({ markets }: MarketGridProps) {
  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
      {markets.map((m) => (
        <div
          key={m.market}
          className={[
            "bg-surface-2 rounded-lg px-3 py-2.5 text-center border",
            m.is_positive_ev ? "border-green-900/60" : "border-edge",
          ].join(" ")}
        >
          <div className="flex items-center justify-center gap-1 mb-1">
            <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">
              {m.label}
            </span>
            {JARGON[m.market] && <Tooltip content={JARGON[m.market]} />}
          </div>
          <p className="text-[18px] font-extrabold text-slate-100 leading-none">
            {formatPercent(m.our_prob)}
          </p>
          <p className="text-[11px] text-slate-500 mt-1">Mkt {formatOdds(m.bookmaker_odds)}</p>
          <p className={`text-[11px] font-bold mt-1 ${evColor(m.ev)}`}>{formatEV(m.ev)}</p>
        </div>
      ))}
    </div>
  )
}
