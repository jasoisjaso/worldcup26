import { api } from "@/lib/api"
import type { HistoryStats } from "@/lib/types"

/**
 * Trust strip. Layer 1.5 of the /match taste pass.
 *
 * Plain-English version of the model track record, sat directly under
 * the verdict. The labels read like a sports-bar friend's quick brag,
 * not a stats table.
 *
 *   "Track record · 50% picks won · 56 graded · +18% profit · behind
 *   the sharps"
 *
 * Renders silently when settled sample < 5. Better silent than broken.
 * SSR component, no client JS shipped.
 */
export async function TrustStrip() {
  let stats: HistoryStats | null = null
  try {
    stats = await api.historyStats()
  } catch {
    return null
  }
  if (!stats || !stats.settled || stats.settled < 5) return null

  const hitPct = (stats.accuracy * 100).toFixed(0)
  const roiPct = (stats.roi * 100).toFixed(0)
  const sample = stats.settled

  // CLV displayed as a signed percent vs closing line. Colour conveys
  // good/neutral/bad — green for +, amber for negative, slate for ~zero.
  // No editorial label ("beating the sharps") because the number is the
  // signal; the label would be filler under the Pinnacle voice rules.
  const clvPctNum = stats.avg_clv != null ? stats.avg_clv * 100 : null
  const clvDisplay = clvPctNum != null
    ? { value: `${clvPctNum >= 0 ? "+" : ""}${clvPctNum.toFixed(1)}%`,
        tone: clvPctNum > 0.5 ? "text-emerald-300"
            : clvPctNum < -1   ? "text-amber-300"
            : "text-slate-300" }
    : null

  const roiTone = stats.roi >= 0 ? "text-emerald-300" : "text-amber-300"
  const roiSign = stats.roi >= 0 ? "+" : ""

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 px-4 py-3 mb-5 flex items-center gap-4 overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">
          Track record
        </span>
      </div>

      <div className="shrink-0">
        <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">{hitPct}%</p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">picks won</p>
      </div>

      <div className="shrink-0">
        <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">{sample}</p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">picks settled</p>
      </div>

      <div className="shrink-0">
        <p className={`text-[14px] font-bold font-mono tabular-nums ${roiTone}`}>
          {roiSign}{roiPct}%
        </p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">profit (flat $1 stake)</p>
      </div>

      {clvDisplay && (
        <div className="shrink-0">
          <p className={`text-[14px] font-bold font-mono tabular-nums ${clvDisplay.tone}`}>
            {clvDisplay.value}
          </p>
          <p className="text-[9px] uppercase tracking-widest text-slate-600">vs closing line</p>
        </div>
      )}

      <a
        href="/history"
        className="ml-auto shrink-0 text-[10px] text-slate-400 hover:text-emerald-300 transition-colors flex items-center gap-1"
      >
        <span>See the full record</span>
        <span aria-hidden>→</span>
      </a>
    </div>
  )
}
