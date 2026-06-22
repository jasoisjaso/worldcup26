"use client"

import { useMemo, useState } from "react"
import type { HistoryEntry } from "@/lib/types"
import { HistoryTable } from "@/components/history/HistoryTable"

/**
 * Filterable track record — slice the logged picks by result, market and sort,
 * with a summary strip that recomputes for the active slice. Pure client-side
 * over the data the page already fetched; no extra requests.
 *
 * The point: a flat chronological list can't answer "how do my 1X2 picks do?"
 * or "what's the ROI on the picks that settled?". The filters make the record
 * actually informative instead of just long.
 */

type ResultFilter = "all" | "won" | "lost" | "pending"
type SortKey = "newest" | "ev" | "biggest_win"

// Group raw market keys into the handful of human buckets people care about.
function marketBucket(market: string): string {
  if (["home_win", "draw", "away_win"].includes(market)) return "Match result"
  if (["1x", "x2", "12"].includes(market)) return "Double chance"
  if (["over_2_5", "under_2_5"].includes(market)) return "Over / Under"
  if (market === "btts") return "BTTS"
  return "Other"
}

const RESULT_TABS: { key: ResultFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "won", label: "Won" },
  { key: "lost", label: "Lost" },
  { key: "pending", label: "Pending" },
]

const SORTS: { key: SortKey; label: string }[] = [
  { key: "newest", label: "Newest" },
  { key: "ev", label: "Best edge" },
  { key: "biggest_win", label: "Biggest odds" },
]

export function TrackRecordFilters({ entries }: { entries: HistoryEntry[] }) {
  const [result, setResult] = useState<ResultFilter>("all")
  const [market, setMarket] = useState<string>("all")
  const [sort, setSort] = useState<SortKey>("newest")

  // Distinct market buckets present in the data (so we only show real options).
  const marketOptions = useMemo(() => {
    const set = new Set(entries.map((e) => marketBucket(e.market)))
    return ["all", ...Array.from(set)]
  }, [entries])

  const filtered = useMemo(() => {
    let rows = entries
    if (result === "won") rows = rows.filter((e) => e.correct === true)
    else if (result === "lost") rows = rows.filter((e) => e.correct === false)
    else if (result === "pending") rows = rows.filter((e) => e.correct == null)
    if (market !== "all") rows = rows.filter((e) => marketBucket(e.market) === market)

    const sorted = [...rows]
    if (sort === "ev") sorted.sort((a, b) => (b.ev ?? 0) - (a.ev ?? 0))
    else if (sort === "biggest_win") sorted.sort((a, b) => (b.bookmaker_odds ?? 0) - (a.bookmaker_odds ?? 0))
    else sorted.sort((a, b) => new Date(b.logged_at).getTime() - new Date(a.logged_at).getTime())
    return sorted
  }, [entries, result, market, sort])

  // Summary for the CURRENT slice — only settled picks count toward hit-rate/ROI.
  const summary = useMemo(() => {
    const settled = filtered.filter((e) => e.correct != null)
    const won = settled.filter((e) => e.correct === true).length
    const pnl = settled.reduce(
      (acc, e) => acc + (e.correct ? (e.bookmaker_odds ?? 1) - 1 : -1),
      0,
    )
    return {
      shown: filtered.length,
      settled: settled.length,
      won,
      hitRate: settled.length ? won / settled.length : null,
      roi: settled.length ? pnl / settled.length : null,
    }
  }, [filtered])

  const chip = (active: boolean) =>
    `text-[11px] font-semibold px-3 py-1.5 rounded-full border transition-colors ${
      active
        ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
        : "border-edge bg-surface-2 text-slate-400 hover:text-slate-200"
    }`

  return (
    <div>
      {/* Filter bar */}
      <div className="space-y-2.5 mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          {RESULT_TABS.map((t) => (
            <button key={t.key} onClick={() => setResult(t.key)} className={chip(result === t.key)}>
              {t.label}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {marketOptions.map((m) => (
            <button key={m} onClick={() => setMarket(m)} className={chip(market === m)}>
              {m === "all" ? "All markets" : m}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[10px] uppercase tracking-wider text-slate-600 mr-1">Sort</span>
          {SORTS.map((s) => (
            <button key={s.key} onClick={() => setSort(s.key)} className={chip(sort === s.key)}>
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* Slice summary — updates with the filter so the record actually informs */}
      <div className="grid grid-cols-4 gap-2 mb-3">
        <div className="rounded-xl border border-edge bg-surface-2 px-3 py-2.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Shown</p>
          <p className="font-mono text-[18px] font-bold text-white tabular-nums">{summary.shown}</p>
          <p className="text-[9px] text-slate-600">{summary.settled} settled</p>
        </div>
        <div className="rounded-xl border border-edge bg-surface-2 px-3 py-2.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Won</p>
          <p className="font-mono text-[18px] font-bold text-white tabular-nums">{summary.won}</p>
          <p className="text-[9px] text-slate-600">of {summary.settled}</p>
        </div>
        <div className="rounded-xl border border-edge bg-surface-2 px-3 py-2.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">Hit rate</p>
          <p className="font-mono text-[18px] font-bold text-white tabular-nums">
            {summary.hitRate == null ? "—" : `${Math.round(summary.hitRate * 100)}%`}
          </p>
        </div>
        <div className="rounded-xl border border-edge bg-surface-2 px-3 py-2.5">
          <p className="text-[9px] uppercase tracking-wider text-slate-600">ROI</p>
          <p
            className={`font-mono text-[18px] font-bold tabular-nums ${
              summary.roi == null ? "text-white" : summary.roi >= 0 ? "text-emerald-400" : "text-rose-400"
            }`}
          >
            {summary.roi == null ? "—" : `${summary.roi >= 0 ? "+" : ""}${(summary.roi * 100).toFixed(1)}%`}
          </p>
          <p className="text-[9px] text-slate-600">flat stakes</p>
        </div>
      </div>

      <HistoryTable entries={filtered} />
    </div>
  )
}
