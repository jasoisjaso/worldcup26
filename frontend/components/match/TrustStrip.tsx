import { api } from "@/lib/api"
import type { HistoryStats } from "@/lib/types"

/**
 * Trust strip — Layer 1.5 of the /match taste pass.
 *
 * Plain-English version of the model track record, sat directly under
 * the verdict. The labels read like a sports-bar friend's quick brag,
 * not a stats table.
 *
 *   "Track record · 50% picks won · 56 graded · +18% profit · vs the
 *    sharp lines we're slightly behind"
 *
 * Renders silently when settled sample < 5 — better silent than broken.
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

  // CLV: positive = our prices beat the sharp closing line (real edge);
  // negative = the sharp line moved past us (the market caught up first).
  // Frame it as "vs the sharps" so it reads without explainer.
  const clvLabel = (() => {
    const v = stats.avg_clv
    if (v == null) return null
    if (v > 0.005)   return { text: "beating the sharps", tone: "text-emerald-300" }
    if (v < -0.01)   return { text: "behind the sharps",  tone: "text-amber-300"  }
    return { text: "matching the sharps", tone: "text-slate-400" }
  })()

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

      {clvLabel && (
        <div className="shrink-0">
          <p className={`text-[12px] font-bold ${clvLabel.tone}`}>
            {clvLabel.text}
          </p>
          <p className="text-[9px] uppercase tracking-widest text-slate-600">vs closing prices</p>
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
