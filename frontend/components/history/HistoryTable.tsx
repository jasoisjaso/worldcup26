import { Flag } from "@/components/common/Flag"
import type { HistoryEntry } from "@/lib/types"
import { formatOdds, formatEV, evColor } from "@/lib/utils"

interface HistoryTableProps {
  entries: HistoryEntry[]
}

export function HistoryTable({ entries }: HistoryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl p-8 text-center text-slate-500 text-sm">
        No predictions logged yet. Predictions are recorded automatically before each kickoff.
      </div>
    )
  }

  return (
    <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl overflow-hidden">
      <div className="grid grid-cols-[32px_1fr_100px_60px_60px_60px_80px] gap-2 px-4 py-2.5 bg-[#0a0d14] border-b border-[#1a2033] text-[10px] font-bold text-slate-600 uppercase tracking-widest">
        <span></span>
        <span>Match</span>
        <span>Pick</span>
        <span>Conf</span>
        <span>Odds</span>
        <span>EV</span>
        <span>Result</span>
      </div>

      {entries.map((entry) => (
        <div
          key={entry.id}
          className="grid grid-cols-[32px_1fr_100px_60px_60px_60px_80px] gap-2 px-4 py-3 border-b border-[#1a2033] last:border-b-0 items-center hover:bg-[#141929] transition-colors"
        >
          <div className="flex gap-0.5">
            <Flag url={entry.home_flag_url} name="" size="sm" />
          </div>
          <div>
            <p className="text-[12px] font-semibold text-slate-200">{entry.match_label}</p>
            <p className="text-[10px] text-slate-600 mt-0.5">
              {new Date(entry.logged_at).toLocaleDateString("en-AU", { month: "short", day: "numeric" })}
            </p>
          </div>
          <div>
            <span className="text-[11px] font-bold bg-blue-950 text-blue-300 border border-blue-800/50 rounded px-1.5 py-0.5">
              {entry.market_label}
            </span>
          </div>
          <p className="text-[12px] font-bold text-slate-200">
            {Math.round(entry.our_probability * 100)}%
          </p>
          <p className="text-[12px] text-slate-400">{formatOdds(entry.bookmaker_odds)}</p>
          <p className={`text-[12px] font-bold ${evColor(entry.ev)}`}>{formatEV(entry.ev)}</p>
          <div>
            {entry.correct === undefined ? (
              <span className="text-[11px] font-semibold bg-slate-900 border border-slate-800 text-slate-500 rounded-full px-2 py-0.5">
                Pending
              </span>
            ) : entry.correct ? (
              <span className="text-[11px] font-semibold bg-green-950 border border-green-800/50 text-green-400 rounded-full px-2 py-0.5">
                Correct
              </span>
            ) : (
              <span className="text-[11px] font-semibold bg-red-950 border border-red-800/50 text-red-400 rounded-full px-2 py-0.5">
                Wrong
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}
