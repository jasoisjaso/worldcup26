import { TopBar } from "@/components/layout/TopBar"
import { ValueList } from "@/components/value/ValueList"
import { EngagementMarker } from "@/components/common/EngagementMarker"
import { api } from "@/lib/api"
import type { ValueOpportunity, Arb, HistoryStats } from "@/lib/types"

import type { Metadata } from "next"

export const dynamic = "force-dynamic"

export const metadata: Metadata = {
  title: "Value Board",
  description: "Live value bets for 2026 FIFA World Cup matches. Where the model thinks the bookies are offering too long a price.",
}

const MARKET_FILTERS = [
  { value: "All", label: "All" },
  { value: "home_win", label: "Home Win" },
  { value: "draw", label: "Draw" },
  { value: "away_win", label: "Away Win" },
  { value: "1x", label: "Home/Draw" },
  { value: "x2", label: "Draw/Away" },
  { value: "over_2_5", label: "Over 2.5" },
  { value: "under_2_5", label: "Under 2.5" },
  { value: "btts", label: "BTTS" },
]

const MATCHDAY_FILTERS = [
  { value: "All", label: "All" },
  { value: "1", label: "MD 1" },
  { value: "2", label: "MD 2" },
  { value: "3", label: "MD 3" },
]

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
          ? "bg-emerald-900/40 border-emerald-700 text-emerald-300"
          : "bg-surface-2 border-edge text-slate-500 hover:text-slate-300",
      ].join(" ")}
    >
      {label}
    </a>
  )
}


export default async function ValuePage({
  searchParams,
}: {
  searchParams: { market?: string; md?: string }
}) {
  let opps: ValueOpportunity[] = []
  let arbs: Arb[] = []
  let stats: HistoryStats | null = null
  try {
    ;[opps, arbs, stats] = await Promise.all([
      api.value(),
      api.arbs().catch(() => []),
      api.historyStats().catch(() => null),
    ])
  } catch {
    opps = []
  }

  const market = searchParams.market ?? "All"
  const md = searchParams.md ?? "All"
  const MAX_SHOWN = 20

  // Trustworthy-first: order by reliability tier, then EV within a tier. Sorting by raw
  // EV alone pushes longshots (highest EV) to the top and into the "Top pick" banner,
  // which defeats the reliability guardrail.
  const TIER: Record<string, number> = { solid: 0, speculative: 1, longshot: 2 }
  const allFiltered = opps
    .filter((o) => market === "All" || o.market === market)
    .filter((o) => md === "All" || String(o.matchday) === md)
    .filter((o) => o.ev >= 0.10 && o.ev <= 1.5 && o.bookmaker_odds <= 10.0)
    .sort((a, b) =>
      (TIER[a.reliability ?? "longshot"] - TIER[b.reliability ?? "longshot"]) || (b.ev - a.ev)
    )

  // Split core (believable, counts to grade) from speculative (user discretion,
  // excluded from the grade). The backend guardrails already dropped the
  // implausible "+68% EV" rejects, so everything here is at least watchable —
  // we just quarantine the speculative ones so they don't look like our A-list.
  const coreAll = allFiltered.filter((o) => o.counts_to_grade !== false && o.grade !== "speculative")
  const specAll = allFiltered.filter((o) => o.counts_to_grade === false || o.grade === "speculative")
  const filtered = coreAll.slice(0, MAX_SHOWN)
  const speculative = specAll.slice(0, MAX_SHOWN)
  const topPick = filtered[0]

  return (
    <>
      <EngagementMarker />
      <TopBar
        title="Value Board"
        subtitle={
          allFiltered.length > 0
            ? `Top ${filtered.length} of ${allFiltered.length} picks where our model sees an edge`
            : "No value detected right now"
        }
      />

      <div className="px-4 py-4">
        <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          Bets where our model thinks the bookie is underestimating a team. Odds above 10.0 excluded.
          <span className="text-slate-300"> A full confidence meter means a believable gap between model and market.</span>
          {" "}Each card shows the best price across Bet365, Sportsbet, and Unibet, and which book has it.
        </div>

        {arbs.length > 0 && (
          <div className="bg-emerald-950/30 border border-emerald-700/50 rounded-xl px-4 py-3 mb-4">
            <p className="text-[10px] text-emerald-400 uppercase tracking-widest font-bold mb-1.5">
              <span aria-hidden="true">◆ </span>Sure bets right now ({arbs.length})
            </p>
            <p className="text-[11px] text-slate-400 mb-2 leading-snug">
              Backing every outcome at the best book guarantees a profit. Rare with three books, so this is usually empty.
            </p>
            <div className="space-y-1.5">
              {arbs.slice(0, 5).map((a, i) => (
                <div key={`${a.match_id}-${a.market}-${i}`} className="text-[12px] text-slate-300">
                  <span className="font-semibold text-white">{a.match_label}</span>
                  <span className="text-slate-500"> · {a.market} · </span>
                  <span className="text-emerald-400 font-bold">+{(a.margin * 100).toFixed(1)}% locked</span>
                  <span className="text-slate-500">
                    {" ("}
                    {a.legs.map((l) => `${l.best_price.toFixed(2)} @ ${l.best_book}`).join(", ")}
                    {")"}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

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
                  The odds feed is quiet right now. Meanwhile every match has a full model
                  prediction on the{" "}
                  <a href="/" className="text-emerald-400 font-semibold hover:underline">Matches page</a>.
                </p>
              </>
            ) : (
              <p className="text-slate-500 text-[14px]">No core picks in this filter.</p>
            )}
          </div>
        ) : (
          <ValueList opps={filtered} tierRecord={stats?.tier_record} />
        )}

        {/* Speculative: the model sees something but we can't fully stand behind
            it. Shown at user discretion and explicitly EXCLUDED from the graded
            track record so a punt the model isn't sure about can't dent the
            scoreboard. */}
        {speculative.length > 0 && (
          <div className="mt-6">
            <div className="bg-amber-950/20 border border-amber-700/30 rounded-xl px-4 py-3 mb-3">
              <p className="text-[10px] text-amber-400 uppercase tracking-widest font-bold mb-1">
                Speculative · {speculative.length} · not graded
              </p>
              <p className="text-[11px] text-slate-400 leading-snug">
                The model sees an edge here, but it&apos;s above the believable band or thin on
                data — we can&apos;t fully stand behind it. Shown for your discretion and kept out
                of the official hit-rate and ROI on the{" "}
                <a href="/performance" className="text-amber-300 hover:underline">Report Card</a>.
                Bet these small, if at all.
              </p>
            </div>
            <ValueList opps={speculative} tierRecord={stats?.tier_record} />
          </div>
        )}
      </div>
    </>
  )
}
