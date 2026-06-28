import { api } from "@/lib/api"
import type { HistoryStats, Calibration } from "@/lib/types"

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
  let calibration: Calibration | null = null
  try {
    ;[stats, calibration] = await Promise.all([
      api.historyStats(),
      api.calibration().catch(() => null),
    ])
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

  // Calibration RPS (DataCamp Idea 2). Unbiased proper score over every
  // snapshotted match that has finished, NOT the +EV-selected pick subset.
  // RPS scale: 0 = perfect, ~0.20 = published WC-predictor benchmark.
  // Lower is better. Suppressed if no completed snapshots yet.
  const rps = (calibration as unknown as { by_market?: { result_1x2?: { rps?: number; n?: number } } } | null)
    ?.by_market?.result_1x2
  const rpsValue = rps?.rps ?? null
  const rpsN = rps?.n ?? null
  // Tone bands: <0.19 green (sharp), 0.19-0.22 slate (par), >0.22 amber (weak).
  const rpsTone = rpsValue == null ? "text-slate-300"
                : rpsValue < 0.19 ? "text-emerald-300"
                : rpsValue > 0.22 ? "text-amber-300"
                : "text-slate-300"

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 px-4 py-3 mb-5 flex items-center gap-4 overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
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

      {rpsValue != null && (
        <div className="shrink-0">
          <p className={`text-[14px] font-bold font-mono tabular-nums ${rpsTone}`}>
            {rpsValue.toFixed(3)}
          </p>
          <p className="text-[9px] uppercase tracking-widest text-slate-600">
            calibration (RPS) {rpsN ? `· ${rpsN}` : ""}
          </p>
        </div>
      )}

      {clvDisplay && (
        <div className="shrink-0">
          <p className={`text-[14px] font-bold font-mono tabular-nums ${clvDisplay.tone}`}>
            {clvDisplay.value}
          </p>
          <p className="text-[9px] uppercase tracking-widest text-slate-600">vs closing line</p>
        </div>
      )}

      <a
        href="/performance"
        className="ml-auto shrink-0 text-[10px] text-slate-400 hover:text-emerald-300 transition-colors flex items-center gap-1"
      >
        <span>See the full record</span>
        <span aria-hidden>→</span>
      </a>
    </div>
  )
}
