import type { HistoryStats } from "@/lib/types"

interface TrackRecordProps {
  stats: HistoryStats
}

export function TrackRecord({ stats }: TrackRecordProps) {
  const items = [
    { value: `${Math.round(stats.accuracy * 100)}%`, label: "Pick accuracy", color: "text-green-400" },
    { value: `+${(stats.avg_ev * 100).toFixed(1)}%`, label: "Avg EV on picks", color: "text-amber-400" },
    { value: `${stats.roi >= 0 ? "+" : ""}${(stats.roi * 100).toFixed(1)}%`, label: "ROI flat stake", color: stats.roi >= 0 ? "text-yellow-400" : "text-red-400" },
    { value: `${stats.correct} / ${stats.total}`, label: "Picks correct", color: "text-slate-200" },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-4">
      {items.map((item) => (
        <div key={item.label} className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3.5">
          <p className={`text-[24px] font-extrabold leading-none ${item.color}`}>{item.value}</p>
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mt-1.5">{item.label}</p>
        </div>
      ))}
    </div>
  )
}
