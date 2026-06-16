import type { HistoryEntry } from "@/lib/types"

/** Cumulative profit in units at flat 1u stakes, indexed by settled pick number (not date,
 *  so idle days don't flatten it). Drawdowns below the prior peak draw in rose. */
export function ProfitCurve({ entries }: { entries: HistoryEntry[] }) {
  const settled = entries
    .filter((e) => e.correct != null && e.bookmaker_odds)
    .slice()
    .reverse() // /history is newest-first; we want chronological
  const n = settled.length

  if (n < 1) {
    return <p className="text-[12px] text-slate-600">No settled picks yet. The profit curve fills in as matches finish.</p>
  }

  let run = 0
  const pts = settled.map((e) => {
    run += e.correct ? e.bookmaker_odds - 1 : -1
    return run
  })
  const final = pts[pts.length - 1]
  const lo = Math.min(0, ...pts)
  const hi = Math.max(0, ...pts)
  const W = 320, H = 170, padL = 34, padR = 12, padT = 14, padB = 22
  const x = (i: number) => padL + (i / Math.max(1, n)) * (W - padL - padR)
  const span = hi - lo || 1
  const y = (v: number) => padT + (1 - (v - lo) / span) * (H - padT - padB)

  // step segments, coloured by whether we're below the running peak (drawdown)
  let peak = 0
  const segs: { x1: number; y1: number; x2: number; y2: number; down: boolean }[] = []
  let prevX = x(0), prevY = y(0)
  pts.forEach((v, i) => {
    peak = Math.max(peak, v)
    const nx = x(i + 1)
    segs.push({ x1: prevX, y1: prevY, x2: nx, y2: prevY, down: v < peak }) // horizontal
    segs.push({ x1: nx, y1: prevY, x2: nx, y2: y(v), down: v < peak })      // step
    prevX = nx; prevY = y(v)
  })

  const tooEarly = n < 50

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <span className={`font-mono tabular-nums text-[26px] font-bold leading-none ${final >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
          {final >= 0 ? "+" : ""}{final.toFixed(1)}u
        </span>
        <span className="text-[11px] text-slate-500">over {n} settled pick{n === 1 ? "" : "s"}</span>
        {tooEarly && (
          <span className="text-[10px] font-semibold text-amber-400 bg-amber-950/40 border border-amber-800/50 rounded px-1.5 py-0.5">early sample</span>
        )}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Cumulative profit curve">
        <line x1={padL} y1={y(0)} x2={W - padR} y2={y(0)} stroke="#26314a" strokeWidth="1" strokeDasharray="3 3" />
        <text x={padL - 6} y={y(hi)} textAnchor="end" dominantBaseline="middle" fill="#5e7099" fontSize="9" fontFamily="monospace">{hi >= 0 ? "+" : ""}{hi.toFixed(0)}u</text>
        <text x={padL - 6} y={y(lo)} textAnchor="end" dominantBaseline="middle" fill="#5e7099" fontSize="9" fontFamily="monospace">{lo.toFixed(0)}u</text>
        {segs.map((s, i) => (
          <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={s.down ? "#f25c6e" : "#10b981"} strokeWidth="1.75" strokeLinecap="round" />
        ))}
      </svg>
      <p className="text-[10px] text-slate-600 mt-1">Units at flat 1u stakes, by pick number. Red stretches are drawdowns below the previous high.</p>
    </div>
  )
}
