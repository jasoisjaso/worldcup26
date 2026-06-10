import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { AccaCombo } from "@/lib/types"

const MATCHDAY_TABS = [
  { value: "All", label: "All MDs" },
  { value: "1", label: "MD 1 Only" },
  { value: "2", label: "MD 2 Only" },
  { value: "3", label: "MD 3 Only" },
]

function ComboCard({
  combo,
  isTop,
}: {
  combo: AccaCombo
  isTop: boolean
}) {
  const stake = 10
  const returns = (stake * combo.combined_odds).toFixed(0)
  const profit = (stake * combo.combined_odds - stake).toFixed(0)
  const legs = combo.legs.length
  const oneInX =
    combo.combined_probability > 0
      ? Math.round(combo.combined_odds)
      : null

  return (
    <div
      className={[
        "border rounded-xl overflow-hidden mb-4",
        isTop
          ? "bg-[#0a1a0f] border-green-800/50"
          : "bg-[#0f1320] border-[#1a2033]",
      ].join(" ")}
    >
      <div
        className={[
          "px-4 py-3 border-b flex items-center justify-between",
          isTop ? "bg-[#071209] border-green-900/50" : "bg-[#0a0d14] border-[#1a2033]",
        ].join(" ")}
      >
        <div>
          {isTop && (
            <p className="text-[9px] font-bold uppercase tracking-widest text-green-500 mb-1">
              Best multi right now
            </p>
          )}
          <span className="text-[13px] font-bold text-white">{legs}-Leg Multi</span>
          {oneInX && (
            <p className="text-[11px] text-slate-500 mt-0.5">
              Hits roughly 1 in {oneInX} times on average
            </p>
          )}
        </div>
      </div>

      <div className="px-4 pt-3 pb-2">
        <div
          className={[
            "rounded-lg px-3 py-2.5 border",
            isTop
              ? "bg-green-950/40 border-green-800/30"
              : "bg-[#080c14] border-[#1a2033]",
          ].join(" ")}
        >
          <p className="text-[13px] text-slate-300">
            <span className="text-white font-bold">${stake} stake</span>
            {" → "}
            <span className={`font-bold text-[15px] ${isTop ? "text-green-400" : "text-slate-200"}`}>
              +${profit}
            </span>
            <span className="text-slate-500"> profit (${returns} back) if all legs win</span>
          </p>
          <p className="text-[10px] text-slate-600 mt-1">
            Combined odds {combo.combined_odds.toFixed(2)} · Place as a {legs}-fold at your bookmaker
          </p>
        </div>
      </div>

      <div className="divide-y divide-[#1a2033] mx-4 mb-3 border border-[#1a2033] rounded-lg overflow-hidden">
        {combo.legs.map((leg, i) => (
          <div key={i} className="px-3 py-2.5 flex items-start justify-between gap-3 bg-[#080c14]">
            <div className="flex items-start gap-2 min-w-0">
              <span className="flex-shrink-0 mt-0.5 w-4 h-4 rounded-full bg-[#1a2033] text-[9px] font-bold text-slate-500 flex items-center justify-center">
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-[12px] font-bold text-white truncate">{leg.label}</p>
                <p className="text-[10px] text-slate-500 truncate mt-0.5">
                  <span className="inline-block bg-[#1a2033] rounded px-1 mr-1 text-[9px] font-bold uppercase tracking-wide">
                    MD{leg.matchday} · Grp {leg.group}
                  </span>
                  {leg.match_label}
                </p>
              </div>
            </div>
            <div className="flex-shrink-0 text-right pt-0.5">
              <p className="text-[13px] font-bold text-white">{leg.bookmaker_odds.toFixed(2)}</p>
            </div>
          </div>
        ))}
      </div>

      <div className="px-4 pb-3">
        <p className="text-[10px] text-slate-600">
          All {legs} results must be correct to collect. Our model rates each of these teams higher than the bookie does.
        </p>
      </div>
    </div>
  )
}

export default async function AccaPage({
  searchParams,
}: {
  searchParams: { k?: string; md?: string }
}) {
  const k = Math.min(5, Math.max(3, parseInt(searchParams.k ?? "5")))
  const md = searchParams.md ?? "All"
  const matchdayParam = md !== "All" ? parseInt(md) : undefined

  let combos: AccaCombo[] = []
  try {
    combos = await api.acca(k, matchdayParam)
  } catch {
    combos = []
  }

  const mdLabel = md === "All" ? "all matchdays" : `Matchday ${md} only`

  return (
    <>
      <TopBar
        title="Multi Builder"
        subtitle="Legs selected where our model sees an edge over the bookie"
      />

      <div className="px-4 py-4">
        <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          Each leg is a match where we think a team is underpriced.
          {" "}<span className="text-slate-300">More legs means a bigger return, but all must win.</span>
          {" "}Odds are the median across Bet365, Sportsbet, and Unibet. Your bookmaker may offer slightly different prices.
        </div>

        {/* Matchday tabs */}
        <div className="mb-3">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">Build from</p>
          <div className="flex gap-1.5 flex-wrap">
            {MATCHDAY_TABS.map((t) => (
              <a
                key={t.value}
                href={`/acca?md=${t.value}&k=${k}`}
                className={[
                  "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                  md === t.value
                    ? "bg-blue-900/40 border-blue-700 text-blue-300"
                    : "bg-[#0f1320] border-[#1a2033] text-slate-500 hover:text-slate-300",
                ].join(" ")}
              >
                {t.label}
              </a>
            ))}
          </div>
        </div>

        {/* Legs tabs */}
        <div className="mb-4">
          <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">Max legs</p>
          <div className="flex gap-1.5">
            {[3, 4, 5].map((n) => (
              <a
                key={n}
                href={`/acca?k=${n}&md=${md}`}
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
        </div>

        {combos.length === 0 ? (
          <div className="text-center py-12">
            <p className="text-slate-500 text-[14px]">
              Not enough value legs from {mdLabel} to build a multi.
              {md !== "All" && " Try the All MDs view for more options."}
            </p>
          </div>
        ) : (
          <div>
            {combos.map((combo, i) => (
              <ComboCard key={i} combo={combo} isTop={i === 0} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
