import type { HistoryStats } from "@/lib/types"

function Tile({
  value, label, sub, tone = "neutral",
}: { value: string; label: string; sub?: string; tone?: "pos" | "neg" | "neutral" }) {
  const num = { pos: "text-emerald-400", neg: "text-rose-400", neutral: "text-white" }[tone]
  const dot = { pos: "bg-emerald-400", neg: "bg-rose-400", neutral: "bg-slate-500" }[tone]
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">{label}</p>
      </div>
      <p className={`font-mono tabular-nums text-[26px] font-bold leading-none ${num}`}>{value}</p>
      {sub && <p className="text-[11px] text-slate-500 mt-1.5">{sub}</p>}
    </div>
  )
}

function EdgeVerdict({ stats }: { stats: HistoryStats }) {
  const clvN = stats.clv_n ?? 0
  const lo = stats.clv_beat_lo
  const hi = stats.clv_beat_hi
  const betsNeeded = stats.bets_to_significance

  // Beating the close, proven: the Wilson lower bound is above a coin flip.
  if (stats.edge_signal === "beating" && lo != null) {
    return (
      <p className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 px-3 py-2 text-[11px] leading-relaxed text-emerald-200/90">
        The model is beating the closing line on {clvN} priced picks (95% lower bound {Math.round(lo * 100)}%,
        above a coin flip). That is the clearest early sign the edge is real, well before win rate or profit can prove it.
      </p>
    )
  }
  if (stats.edge_signal === "lagging" && hi != null) {
    return (
      <p className="rounded-lg border border-rose-500/30 bg-rose-500/5 px-3 py-2 text-[11px] leading-relaxed text-rose-200/80">
        Not beating the closing line yet over {clvN} priced picks (95% upper bound {Math.round(hi * 100)}%). Treat
        the win rate and ROI below as noise until closing-line value turns positive.
      </p>
    )
  }
  // Still building: be explicit about how much more it takes.
  return (
    <p className="rounded-lg border border-edge bg-surface-2 px-3 py-2 text-[11px] leading-relaxed text-slate-400">
      Early sample ({stats.total} pick{stats.total === 1 ? "" : "s"}). Hit rate and ROI swing hard on this few results
      {betsNeeded ? <>, and the ROI would need roughly {betsNeeded.toLocaleString()} settled bets before its range clears zero</> : null}.
      Read them as a running scoreboard, not a verdict. Beating the closing line is the steadier signal and is still building.
    </p>
  )
}

export function TrackRecord({ stats }: { stats: HistoryStats }) {
  const hasClv = stats.clv_n != null && stats.clv_n > 0
  const roiPos = stats.roi >= 0
  const roiCi = stats.roi_ci != null ? `±${(stats.roi_ci * 100).toFixed(1)}% (95%)` : "flat 1-unit stakes"
  const beatSub =
    stats.clv_beat_lo != null && stats.clv_beat_hi != null
      ? `95% CI ${Math.round(stats.clv_beat_lo * 100)}-${Math.round(stats.clv_beat_hi * 100)}%`
      : `${stats.clv_n} priced vs closing line`

  return (
    <div className="space-y-2.5">
      {stats.total > 0 && <EdgeVerdict stats={stats} />}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5">
        <Tile
          value={stats.total > 0 ? `${Math.round(stats.accuracy * 100)}%` : "-"}
          label="Hit rate"
          sub={`${stats.correct} correct so far`}
          tone={stats.accuracy >= 0.5 ? "pos" : "neutral"}
        />
        <Tile
          value={stats.total > 0 ? `${roiPos ? "+" : ""}${(stats.roi * 100).toFixed(1)}%` : "-"}
          label="ROI"
          sub={roiCi}
          tone={stats.total > 0 ? (roiPos ? "pos" : "neg") : "neutral"}
        />
        <Tile
          value={`${(stats.avg_ev * 100).toFixed(1)}%`}
          label="Avg edge"
          sub="model vs the bookie line"
          tone="neutral"
        />
        {hasClv ? (
          <Tile
            value={`${Math.round((stats.clv_beat_close_rate ?? 0) * 100)}%`}
            label="Beat the close"
            sub={beatSub}
            tone={stats.edge_signal === "beating" ? "pos" : stats.edge_signal === "lagging" ? "neg" : "neutral"}
          />
        ) : (
          <Tile value={`${stats.total}`} label="Picks logged" sub="all before kickoff" tone="neutral" />
        )}
      </div>
    </div>
  )
}
