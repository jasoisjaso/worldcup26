import { TopBar } from "@/components/layout/TopBar"
import { ShareButton } from "@/components/common/ShareButton"
import { MultiBuilder } from "@/components/acca/MultiBuilder"
import { api } from "@/lib/api"
import type { AccaCombo, Match } from "@/lib/types"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Acca Builder",
  description: "Build 2-5 leg accumulators from value picks across WC 2026 group stage matchdays. Pre-built combos, odds up to 8.0, or build your own with correlation-correct pricing.",
}

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
  // Our model's probability the whole multi lands vs what the bookie's combined odds imply.
  const modelPct = Math.round(combo.combined_probability * 100)
  const bookieImpliedPct = Math.round((1 / combo.combined_odds) * 100)

  return (
    <div
      className={[
        "border rounded-xl overflow-hidden mb-4",
        isTop
          ? "bg-[#0a1a0f] border-green-800/50"
          : "bg-surface-2 border-edge",
      ].join(" ")}
    >
      <div
        className={[
          "px-4 py-3 border-b flex items-center justify-between",
          isTop ? "bg-[#071209] border-green-900/50" : "bg-surface-0 border-edge",
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
              Bookie&apos;s odds imply ~1 in {oneInX}
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
              : "bg-surface-1 border-edge",
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
          {combo.kelly_pct != null && combo.kelly_pct > 0 && (
            <p className="text-[10px] text-slate-500 mt-1">
              Model-suggested stake: <span className="text-slate-300 font-semibold">{combo.kelly_pct}%</span> of
              bankroll (fractional Kelly, trimmed harder per extra leg since multi errors compound)
            </p>
          )}
          <div className="flex items-center gap-2 mt-2 pt-2 border-t border-edge text-[10px]">
            <span className="text-slate-500">Our model:</span>
            <span className="text-white font-bold">{modelPct}%</span>
            <span className="text-slate-600">vs bookie implies</span>
            <span className="text-slate-300 font-semibold">{bookieImpliedPct}%</span>
            {modelPct > bookieImpliedPct && (
              <span className="ml-auto text-green-400 font-bold">+{modelPct - bookieImpliedPct} pt edge</span>
            )}
          </div>
        </div>
      </div>

      <div className="divide-y divide-edge mx-4 mb-3 border border-edge rounded-lg overflow-hidden">
        {combo.legs.map((leg, i) => (
          <div key={i} className="px-3 py-2.5 flex items-start justify-between gap-3 bg-surface-1">
            <div className="flex items-start gap-2 min-w-0">
              <span className="flex-shrink-0 mt-0.5 w-4 h-4 rounded-full bg-edge text-[9px] font-bold text-slate-500 flex items-center justify-center">
                {i + 1}
              </span>
              <div className="min-w-0">
                <p className="text-[12px] font-bold text-white truncate">{leg.label}</p>
                <p className="text-[10px] text-slate-500 truncate mt-0.5">
                  <span className="inline-block bg-edge rounded px-1 mr-1 text-[9px] font-bold uppercase tracking-wide">
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

      <div className="px-4 pb-3 flex items-center justify-between gap-2">
        <p className="text-[10px] text-slate-600">
          All {legs} results must be correct to collect. Our model rates each of these teams higher than the bookie does.
        </p>
        <ShareButton
          title="WC2026 Multi Pick"
          text={[
            `WC2026 Multi: ${legs} legs @ ${combo.combined_odds.toFixed(2)}`,
            ...combo.legs.map((leg, i) => `${i + 1}. ${leg.label}`),
          ].join("\n")}
          url="https://wc26.tinjak.com/acca"
          label="Share"
        />
      </div>
    </div>
  )
}

type AccaSearch = { tab?: string; k?: string; md?: string }

const TOP_TABS = [
  { value: "model",  label: "Model's picks" },
  { value: "custom", label: "Build your own" },
]

export default async function AccaPage({
  searchParams,
}: {
  searchParams: AccaSearch
}) {
  const tab = searchParams.tab === "custom" ? "custom" : "model"

  return (
    <>
      <TopBar
        title="Acca Builder"
        subtitle={
          tab === "custom"
            ? "Drop in any legs, see the model's verdict + the best swap"
            : "Legs selected where our model sees an edge over the bookie"
        }
      />

      <div className="px-4 py-4">
        <div className="flex gap-1.5 mb-4">
          {TOP_TABS.map((t) => (
            <a
              key={t.value}
              href={`/acca?tab=${t.value}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[12px] font-semibold border transition-colors",
                tab === t.value
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              {t.label}
            </a>
          ))}
        </div>

        {tab === "custom" ? (
          <CustomTab />
        ) : (
          <ModelTab searchParams={searchParams} />
        )}
      </div>
    </>
  )
}

async function CustomTab() {
  let matches: Match[] = []
  try {
    matches = await api.matches()
  } catch {
    matches = []
  }
  // Only upcoming matches are priceable.
  const upcoming = matches.filter((m) => m.status === "upcoming")
  if (upcoming.length === 0) {
    return (
      <div className="text-center py-12 px-6">
        <p className="text-slate-400 text-[14px] font-semibold mb-1">No upcoming matches</p>
        <p className="text-slate-500 text-[12px] leading-relaxed max-w-sm mx-auto">
          The slate is empty right now. Check back when fixtures are loaded.
        </p>
      </div>
    )
  }
  return <MultiBuilder matches={upcoming} />
}

async function ModelTab({ searchParams }: { searchParams: AccaSearch }) {
  const k = Math.min(5, Math.max(3, parseInt(searchParams.k ?? "5")))
  const md = searchParams.md ?? "All"
  const matchdayParam = md !== "All" ? parseInt(md) : undefined

  let combos: AccaCombo[] = []
  try {
    combos = await api.acca(k, matchdayParam)
  } catch {
    combos = []
  }

  return (
    <>
      <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
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
              href={`/acca?tab=model&md=${t.value}&k=${k}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                md === t.value
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
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
              href={`/acca?tab=model&k=${n}&md=${md}`}
              className={[
                "px-3 py-1.5 rounded-lg text-[11px] font-semibold border transition-colors",
                k === n
                  ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
                  : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
              ].join(" ")}
            >
              Up to {n} legs
            </a>
          ))}
        </div>
      </div>

      {combos.length === 0 ? (
        <div className="text-center py-12 px-6">
          <p className="text-slate-400 text-[14px] font-semibold mb-1">No multis to build right now</p>
          <p className="text-slate-500 text-[12px] leading-relaxed max-w-sm mx-auto">
            Multis are built from value legs, which need live bookmaker odds to find. The odds
            feed is quiet at the moment{md !== "All" ? ", and this is filtered to a single matchday" : ""}.
            See the model&apos;s match predictions on the{" "}
            <a href="/" className="text-emerald-400 font-semibold hover:underline">Matches page</a>.
            {" "}Or try the <a href="/acca?tab=custom" className="text-emerald-400 font-semibold hover:underline">Build your own</a> tab.
          </p>
        </div>
      ) : (
        <div>
          {combos.map((combo, i) => (
            <ComboCard key={i} combo={combo} isTop={i === 0} />
          ))}
        </div>
      )}
    </>
  )
}
