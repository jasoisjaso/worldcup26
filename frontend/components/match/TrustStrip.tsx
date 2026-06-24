import { api } from "@/lib/api"
import type { HistoryStats } from "@/lib/types"

/**
 * Trust strip — Layer 1.5 of the /match taste pass.
 *
 * A single horizontal strip directly under the verdict that says: "this
 * model has a track record, here it is." Borrowed from FiveThirtyEight's
 * About page calibration histogram and Opta's supercomputer brand — the
 * brand asset that earns the verdict line credibility.
 *
 * Renders silently when the API call fails or no picks have settled
 * (early-tournament empty state), so the page never shows broken trust
 * signals — better to omit than to print "—".
 *
 * SSR component — fetches on the server, no client JS shipped.
 */
export async function TrustStrip() {
  let stats: HistoryStats | null = null
  try {
    stats = await api.historyStats()
  } catch {
    return null
  }
  if (!stats || !stats.settled || stats.settled < 5) return null

  const hitPct = (stats.accuracy * 100).toFixed(1)
  const clvPct = stats.avg_clv != null ? (stats.avg_clv * 100).toFixed(1) : null
  const roiPct = (stats.roi * 100).toFixed(1)
  const sample = stats.settled

  // CLV beats win-rate as a trust signal at small samples — it's the sharp
  // bookmakers' opinion of our pick price vs theirs, and accumulates faster.
  // The label adapts: positive CLV → "beating the close" (strongest claim).
  const clvLabel =
    stats.avg_clv == null ? null
    : stats.avg_clv > 0.005 ? { text: "beating close", tone: "text-emerald-300" }
    : stats.avg_clv < -0.01 ? { text: "trailing close", tone: "text-amber-300" }
    : { text: "neutral CLV", tone: "text-slate-400" }

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 px-4 py-3 mb-5 flex items-center gap-4 overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        <span className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500">
          This model
        </span>
      </div>

      <div className="shrink-0">
        <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">{hitPct}%</p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">hit rate</p>
      </div>

      <div className="shrink-0">
        <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">{sample}</p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">picks graded</p>
      </div>

      <div className="shrink-0">
        <p className={`text-[14px] font-bold font-mono tabular-nums ${parseFloat(roiPct) >= 0 ? "text-emerald-300" : "text-amber-300"}`}>
          {parseFloat(roiPct) >= 0 ? "+" : ""}{roiPct}%
        </p>
        <p className="text-[9px] uppercase tracking-widest text-slate-600">ROI flat-stake</p>
      </div>

      {clvPct != null && clvLabel && (
        <div className="shrink-0">
          <p className={`text-[14px] font-bold font-mono tabular-nums ${clvLabel.tone}`}>
            {stats.avg_clv! >= 0 ? "+" : ""}{clvPct}%
          </p>
          <p className="text-[9px] uppercase tracking-widest text-slate-600">{clvLabel.text}</p>
        </div>
      )}

      <a
        href="/history"
        className="ml-auto shrink-0 text-[10px] text-slate-400 hover:text-emerald-300 transition-colors flex items-center gap-1"
      >
        <span>How is this calculated?</span>
        <span aria-hidden>→</span>
      </a>
    </div>
  )
}
