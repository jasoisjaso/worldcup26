import { Flag } from "@/components/common/Flag"
import type { HistoryEntry } from "@/lib/types"
import { formatOdds, formatEV, evColor } from "@/lib/utils"

interface HistoryTableProps {
  entries: HistoryEntry[]
}

function ResultBadge({ correct }: { correct: boolean | null | undefined }) {
  if (correct == null) {
    return (
      <span className="text-[11px] font-semibold bg-slate-900 border border-slate-800 text-slate-500 rounded-full px-2 py-0.5 whitespace-nowrap">
        Pending
      </span>
    )
  }
  if (correct) {
    return (
      <span className="text-[11px] font-semibold bg-green-950 border border-green-800/50 text-green-400 rounded-full px-2 py-0.5 whitespace-nowrap">
        Correct
      </span>
    )
  }
  return (
    <span className="text-[11px] font-semibold bg-red-950 border border-red-800/50 text-red-400 rounded-full px-2 py-0.5 whitespace-nowrap">
      Wrong
    </span>
  )
}

export function HistoryTable({ entries }: HistoryTableProps) {
  if (entries.length === 0) {
    return (
      <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 p-8 text-center text-slate-500 text-sm">
        No picks logged yet. Predictions are recorded automatically before each kickoff.
      </div>
    )
  }

  return (
    <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 overflow-hidden">
      {/* Desktop header, hidden on mobile */}
      <div className="hidden sm:grid grid-cols-[28px_1fr_130px_56px_56px_56px_80px] gap-2 px-4 py-2.5 bg-surface-0 border-b border-edge text-[10px] font-bold text-slate-600 uppercase tracking-widest">
        <span></span>
        <span>Match</span>
        <span>Pick</span>
        <span>Conf</span>
        <span>Odds</span>
        <span>EV</span>
        <span>Result</span>
      </div>

      {entries.map((entry) => (
        <div key={entry.id} className="border-b border-edge last:border-b-0">
          {/* Desktop row */}
          <div className="hidden sm:grid grid-cols-[28px_1fr_130px_56px_56px_56px_80px] gap-2 px-4 py-3 items-center hover:bg-surface-2 transition-colors">
            <div>
              <Flag url={entry.home_flag_url} name="" size="sm" />
            </div>
            <div>
              <p className="text-[12px] font-semibold text-slate-200 truncate">{entry.match_label}</p>
              <p className="text-[10px] text-slate-600 mt-0.5">
                {new Date(entry.logged_at).toLocaleDateString("en-AU", { month: "short", day: "numeric" })}
              </p>
            </div>
            <div>
              <span className="text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-blue-800/50 rounded px-1.5 py-0.5 truncate block max-w-full">
                {entry.pick_label}
              </span>
            </div>
            <p className="text-[12px] font-bold text-slate-200">
              {Math.round(entry.our_probability * 100)}%
            </p>
            <p className="text-[12px] text-slate-400">{formatOdds(entry.bookmaker_odds)}</p>
            <p className={`text-[12px] font-bold ${evColor(entry.ev)}`}>{formatEV(entry.ev)}</p>
            <ResultBadge correct={entry.correct} />
          </div>

          {/* Mobile card */}
          <div className="sm:hidden px-4 py-3 hover:bg-surface-2 transition-colors">
            <div className="flex items-start justify-between gap-2 mb-2">
              <div className="flex items-center gap-2 min-w-0">
                <Flag url={entry.home_flag_url} name="" size="sm" />
                <div className="min-w-0">
                  <p className="text-[12px] font-semibold text-slate-200 truncate">{entry.match_label}</p>
                  <p className="text-[10px] text-slate-600 mt-0.5">
                    {new Date(entry.logged_at).toLocaleDateString("en-AU", { month: "short", day: "numeric" })}
                  </p>
                </div>
              </div>
              <ResultBadge correct={entry.correct} />
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-[11px] font-bold bg-emerald-950 text-emerald-300 border border-blue-800/50 rounded px-1.5 py-0.5">
                {entry.pick_label}
              </span>
              <span className="text-[11px] text-slate-400">
                {Math.round(entry.our_probability * 100)}% confidence
              </span>
              <span className="text-[11px] text-slate-500">
                @ {formatOdds(entry.bookmaker_odds)}
              </span>
              <span className={`text-[11px] font-bold ${evColor(entry.ev)}`}>
                {formatEV(entry.ev)} EV
              </span>
            </div>
          </div>
        </div>
      ))}
    </div>
  )
}
