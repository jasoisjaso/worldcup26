import type { HistoryEntry } from "@/lib/types"

/** Closing Line Value: each pick plotted as our price vs the closing line (in implied
 *  probability). Dots below the break-even diagonal = we locked a better price than the
 *  market closed at, the clearest proof an edge is real. */
export function ClvScatter({ entries }: { entries: HistoryEntry[] }) {
  const pts = entries
    .filter((e) => e.closing_odds != null && e.closing_odds > 1 && e.bookmaker_odds > 1)
    .map((e) => ({
      x: 1 / e.bookmaker_odds,          // our implied prob
      y: 1 / (e.closing_odds as number), // closing implied prob
      beat: (e.clv ?? 0) > 0.001,
      miss: (e.clv ?? 0) < -0.001,
    }))

  if (pts.length < 1) {
    return <p className="text-[12px] text-slate-600">CLV plots once picks reach kickoff and the closing line is captured.</p>
  }

  const S = 240, pad = 30
  const inner = S - pad * 2
  const px = (v: number) => pad + v * inner
  const py = (v: number) => pad + (1 - v) * inner
  const beatN = pts.filter((p) => p.beat).length

  return (
    <div>
      <div className="flex items-baseline gap-2 mb-1">
        <span className="font-mono tabular-nums text-[20px] font-bold text-white leading-none">{Math.round((beatN / pts.length) * 100)}%</span>
        <span className="text-[11px] text-slate-500">beat the close ({pts.length} priced)</span>
      </div>
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[300px] mx-auto" role="img" aria-label="Closing line value scatter">
        {[0.25, 0.5, 0.75].map((g) => (
          <g key={g}>
            <line x1={px(g)} y1={pad} x2={px(g)} y2={S - pad} stroke="#1a2233" strokeWidth="1" />
            <line x1={pad} y1={py(g)} x2={S - pad} y2={py(g)} stroke="#1a2233" strokeWidth="1" />
          </g>
        ))}
        <rect x={pad} y={pad} width={inner} height={inner} fill="none" stroke="#26314a" strokeWidth="1" />
        {/* break-even diagonal */}
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="#475569" strokeWidth="1.25" strokeDasharray="4 4" />
        {pts.map((p, i) => (
          <circle key={i} cx={px(p.x)} cy={py(p.y)} r="4" fillOpacity="0.85"
                  fill={p.beat ? "#10b981" : p.miss ? "#f25c6e" : "#64748b"} stroke="#080b12" strokeWidth="0.75" />
        ))}
        <text x={S - pad} y={S - pad + 14} textAnchor="end" fill="#34d399" fontSize="8.5" fontWeight="600">we beat the close ↓</text>
        <text x={pad} y={pad - 8} textAnchor="start" fill="#94a3b8" fontSize="8.5" fontWeight="600">market beat us ↑</text>
        <text x={S / 2} y={S - 5} textAnchor="middle" fill="#5e7099" fontSize="9" fontWeight="600">OUR PRICE →</text>
        <text x={11} y={S / 2} textAnchor="middle" fill="#5e7099" fontSize="9" fontWeight="600" transform={`rotate(-90 11 ${S / 2})`}>CLOSING PRICE →</text>
      </svg>
      <p className="text-[10px] text-slate-600 mt-1">Each dot is one pick. Below the dashed line, we locked a longer price than the market closed at.</p>
    </div>
  )
}
