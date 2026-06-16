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

export function TrackRecord({ stats }: { stats: HistoryStats }) {
  const hasClv = stats.clv_n != null && stats.clv_n > 0
  const roiPos = stats.roi >= 0

  return (
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
        sub="flat 1-unit stakes"
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
          sub={`${stats.clv_n} priced vs closing line`}
          tone={(stats.clv_beat_close_rate ?? 0) >= 0.5 ? "pos" : "neg"}
        />
      ) : (
        <Tile value={`${stats.total}`} label="Picks logged" sub="all before kickoff" tone="neutral" />
      )}
    </div>
  )
}
