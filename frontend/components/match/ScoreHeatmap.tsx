import type { ScoreGrid } from "@/lib/types"

/** Dixon-Coles score-line probability matrix as a heatmap: home goals down, away goals
 *  across, cell intensity = probability. The model's whole scoreline distribution at a
 *  glance, the way StatsBomb shows a shot map. */
export function ScoreHeatmap({
  grid, homeName, awayName,
}: { grid: ScoreGrid; homeName: string; awayName: string }) {
  const { grid: g, max, peak } = grid
  const n = max + 1

  // top 3 scorelines for the caption
  const flat: { i: number; j: number; p: number }[] = []
  g.forEach((row, i) => row.forEach((p, j) => flat.push({ i, j, p })))
  const top = [...flat].sort((a, b) => b.p - a.p).slice(0, 3)
  const peakCell = top[0]

  const alpha = (p: number) => (peak > 0 ? Math.pow(p / peak, 0.65) : 0)

  return (
    <div>
      <div className="flex items-end gap-2 mb-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500">Score-line probability</p>
        <p className="text-[10px] text-slate-600">brighter = more likely</p>
      </div>

      <div className="flex gap-1.5">
        {/* y-axis label (home goals) */}
        <div className="flex flex-col items-center justify-center">
          <span className="text-[9px] font-semibold text-emerald-400/70 uppercase tracking-wider [writing-mode:vertical-rl] rotate-180 whitespace-nowrap">
            {homeName} goals
          </span>
        </div>

        <div className="flex-1 min-w-0">
          {/* grid */}
          <div className="grid gap-[3px]" style={{ gridTemplateColumns: `repeat(${n}, minmax(0,1fr))` }}>
            {g.map((row, i) =>
              row.map((p, j) => {
                const isPeak = i === peakCell.i && j === peakCell.j
                const isDraw = i === j
                return (
                  <div
                    key={`${i}-${j}`}
                    title={`${i}-${j}: ${(p * 100).toFixed(1)}%`}
                    className={[
                      "aspect-square rounded-[3px] flex items-center justify-center relative",
                      isPeak ? "ring-2 ring-emerald-300" : "",
                      isDraw ? "outline outline-1 outline-white/10" : "",
                    ].join(" ")}
                    style={{ backgroundColor: `rgba(16,185,129,${alpha(p).toFixed(3)})` }}
                  >
                    {p >= 0.04 && (
                      <span className={`font-mono tabular-nums text-[9px] sm:text-[10px] ${alpha(p) > 0.5 ? "text-[#03110b] font-bold" : "text-slate-300"}`}>
                        {Math.round(p * 100)}
                      </span>
                    )}
                  </div>
                )
              })
            )}
          </div>
          {/* x-axis ticks (away goals) */}
          <div className="grid gap-[3px] mt-1" style={{ gridTemplateColumns: `repeat(${n}, minmax(0,1fr))` }}>
            {Array.from({ length: n }).map((_, j) => (
              <span key={j} className="text-center font-mono text-[9px] text-slate-600">{j}</span>
            ))}
          </div>
          <p className="text-center text-[9px] font-semibold text-orange-400/70 uppercase tracking-wider mt-1">
            {awayName} goals
          </p>
        </div>
      </div>

      <p className="text-[11px] text-slate-500 mt-3 leading-snug">
        Most likely:{" "}
        {top.map((s, i) => (
          <span key={`${s.i}-${s.j}`}>
            <span className="font-mono tabular-nums text-slate-200">{s.i}-{s.j}</span>
            <span className="text-slate-600"> {Math.round(s.p * 100)}%</span>
            {i < top.length - 1 ? <span className="text-slate-700">, </span> : null}
          </span>
        ))}
        . Outlined cells are draws.
      </p>
    </div>
  )
}
