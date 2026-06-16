/** Total-goals distribution, summed off the score-line grid (anti-diagonals). Clean column
 *  chart with the Over/Under 2.5 line marked. */
export function GoalsDistribution({ grid }: { grid: number[][] }) {
  const cap = 5
  const totals = Array(cap + 2).fill(0) // 0..5 exact, last = 6+
  grid.forEach((row, i) =>
    row.forEach((p, j) => {
      const t = i + j
      totals[Math.min(t, cap + 1)] += p
    })
  )
  const labels = Array.from({ length: cap + 1 }, (_, i) => String(i)).concat(`${cap + 1}+`)
  const max = Math.max(...totals, 0.0001)
  const over25 = totals.slice(3).reduce((a, b) => a + b, 0)

  return (
    <div>
      <div className="flex items-end gap-2 mb-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Total goals</p>
        <p className="text-[10px] text-slate-600">over 2.5 = {Math.round(over25 * 100)}%</p>
      </div>
      <div className="flex items-end gap-1.5 h-28 relative">
        {/* O/U 2.5 boundary between t=2 and t=3 */}
        <div className="absolute inset-y-0 border-l border-dashed border-orange-400/50 pointer-events-none"
             style={{ left: `${(3 / (cap + 2)) * 100}%` }} />
        {totals.map((p, t) => (
          <div key={t} className="flex-1 flex flex-col items-center justify-end h-full" title={`${labels[t]} goals: ${(p * 100).toFixed(1)}%`}>
            <span className="font-mono tabular-nums text-[9px] text-slate-400 mb-1">{Math.round(p * 100)}</span>
            <div
              className={`w-full rounded-t ${t >= 3 ? "bg-emerald-500" : "bg-emerald-500/55"}`}
              style={{ height: `${Math.max((p / max) * 100, 2)}%` }}
            />
            <span className="font-mono text-[9px] text-slate-600 mt-1">{labels[t]}</span>
          </div>
        ))}
      </div>
      <p className="text-[10px] text-slate-600 mt-2">Brighter bars are 3+ goals (over 2.5). Dashed line is the O/U 2.5 split.</p>
    </div>
  )
}
