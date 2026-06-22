type Band = { band: string; n: number; hit_rate: number; expected: number }

/**
 * Confidence-band reliability strip. For each probability band the model has
 * predicted in, shows what it SAID (mean predicted prob) vs what HAPPENED
 * (realised hit-rate), with the sample size. The honest "when we said ~60%, it
 * landed X% of the time" read — straight from the settled track record.
 *
 * Calibrated = the two bars are close. A realised bar well below predicted in a
 * band means the model is overconfident there (and we should trust it less).
 */
export function ConfidenceBands({ data }: { data: { total: number; bands: Band[] } | null }) {
  if (!data || data.total === 0 || data.bands.length === 0) {
    return (
      <div className="h-[120px] flex items-center justify-center text-[12px] text-slate-600 text-center px-4">
        Fills in as matches are scored — shows how often each confidence level actually lands.
      </div>
    )
  }

  return (
    <div className="space-y-2.5">
      {data.bands.map((b) => {
        const predicted = Math.round(b.expected * 100)
        const realised = Math.round(b.hit_rate * 100)
        // Gap between predicted and realised → how calibrated this band is.
        const gap = Math.abs(predicted - realised)
        const tone = gap <= 8 ? "text-emerald-400" : gap <= 18 ? "text-amber-400" : "text-rose-400"
        return (
          <div key={b.band}>
            <div className="flex items-center justify-between text-[10px] mb-1">
              <span className="font-mono text-slate-300">{b.band} confidence</span>
              <span className="text-slate-600">n={b.n}</span>
            </div>
            {/* Predicted (hollow) vs realised (filled) on the same track. */}
            <div className="relative h-4 rounded bg-surface-3 overflow-hidden">
              {/* predicted marker line */}
              <div className="absolute top-0 bottom-0 w-0.5 bg-slate-500/70 z-10" style={{ left: `${predicted}%` }} title={`Predicted ${predicted}%`} />
              {/* realised fill */}
              <div className="h-full bg-emerald-500/50 rounded" style={{ width: `${realised}%` }} />
              <div className="absolute inset-0 flex items-center justify-end pr-1.5">
                <span className={`font-mono text-[9px] tabular-nums ${tone}`}>
                  said {predicted}% · landed {realised}%
                </span>
              </div>
            </div>
          </div>
        )
      })}
      <p className="text-[10px] text-slate-600 leading-snug pt-1">
        The line is what the model said; the green bar is what actually happened. Close together =
        well-calibrated at that confidence level. Small samples swing — read the n.
      </p>
    </div>
  )
}
