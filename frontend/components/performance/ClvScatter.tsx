"use client"
import { useState } from "react"
import type { HistoryEntry } from "@/lib/types"

/** Closing Line Value: each pick plotted as our price vs the closing line (in implied
 *  probability). Dots below the break-even diagonal = we locked a better price than the
 *  market closed at, the clearest proof an edge is real. Tap a dot to read the pick. */
export function ClvScatter({ entries }: { entries: HistoryEntry[] }) {
  const [active, setActive] = useState<number | null>(null)

  const pts = entries
    .filter((e) => e.closing_odds != null && e.closing_odds > 1 && e.bookmaker_odds > 1)
    .map((e) => ({
      x: 1 / e.bookmaker_odds,
      y: 1 / (e.closing_odds as number),
      beat: (e.clv ?? 0) > 0.001,
      miss: (e.clv ?? 0) < -0.001,
      label: e.pick_label || e.market_label,
      match: e.match_label,
      took: e.bookmaker_odds,
      closed: e.closing_odds as number,
      clv: e.clv ?? 0,
    }))

  if (pts.length < 1) {
    return <p className="text-[12px] text-slate-600">CLV plots once picks reach kickoff and the closing line is captured.</p>
  }

  const S = 240, pad = 30
  const inner = S - pad * 2
  const px = (v: number) => pad + v * inner
  const py = (v: number) => pad + (1 - v) * inner
  const beatN = pts.filter((p) => p.beat).length
  const a = active != null ? pts[active] : null

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
        <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="#475569" strokeWidth="1.25" strokeDasharray="4 4" />
        {pts.map((p, i) => (
          <circle
            key={i} cx={px(p.x)} cy={py(p.y)} r={active === i ? 6 : 4}
            fillOpacity={active === null || active === i ? 0.9 : 0.35}
            fill={p.beat ? "#10b981" : p.miss ? "#f25c6e" : "#64748b"}
            stroke={active === i ? "#ffffff" : "#080b12"} strokeWidth={active === i ? 1.5 : 0.75}
            className="cursor-pointer"
            onClick={() => setActive(active === i ? null : i)}
            onMouseEnter={() => setActive(i)}
          />
        ))}
        <text x={S - pad} y={S - pad + 14} textAnchor="end" fill="#34d399" fontSize="8.5" fontWeight="600">we beat the close ↓</text>
        <text x={pad} y={pad - 8} textAnchor="start" fill="#94a3b8" fontSize="8.5" fontWeight="600">market beat us ↑</text>
        <text x={S / 2} y={S - 5} textAnchor="middle" fill="#5e7099" fontSize="9" fontWeight="600">OUR PRICE →</text>
        <text x={11} y={S / 2} textAnchor="middle" fill="#5e7099" fontSize="9" fontWeight="600" transform={`rotate(-90 11 ${S / 2})`}>CLOSING PRICE →</text>
      </svg>
      <p className="text-[11px] mt-1 min-h-[2.4em] leading-snug">
        {a ? (
          <span className="text-slate-300">
            {a.match} <span className="text-slate-500">·</span> {a.label}: took{" "}
            <span className="font-mono text-slate-200">{a.took.toFixed(2)}</span>, closed{" "}
            <span className="font-mono text-slate-200">{a.closed.toFixed(2)}</span>{" "}
            <span className={a.clv > 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
              {a.clv > 0 ? "+" : ""}{(a.clv * 100).toFixed(1)}% CLV
            </span>
          </span>
        ) : (
          <span className="text-slate-600">Tap a dot to read that pick. Below the dashed line means we locked a longer price than the market closed at.</span>
        )}
      </p>
    </div>
  )
}
