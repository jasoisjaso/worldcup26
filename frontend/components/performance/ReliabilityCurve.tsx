"use client"
import { useState } from "react"
import type { ReliabilityBin } from "@/lib/types"

/** Calibration plot: where the dots sit on the diagonal, the stated probabilities match
 *  reality. Above the line = the model was too cautious; below = overconfident. Tap a
 *  point to read what the model said versus what actually happened. */
export function ReliabilityCurve({ bins }: { bins: ReliabilityBin[] }) {
  const [active, setActive] = useState<number | null>(null)
  const S = 240
  const pad = 28
  const inner = S - pad * 2
  const x = (v: number) => pad + v * inner
  const y = (v: number) => pad + (1 - v) * inner
  const pts = bins.filter((b) => b.n > 0)
  const maxN = Math.max(1, ...pts.map((b) => b.n))
  const a = active != null ? pts[active] : null

  return (
    <div>
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[300px] mx-auto" role="img" aria-label="Calibration reliability curve">
        {[0.25, 0.5, 0.75].map((g) => (
          <g key={g}>
            <line x1={x(g)} y1={pad} x2={x(g)} y2={S - pad} stroke="#1a2233" strokeWidth="1" />
            <line x1={pad} y1={y(g)} x2={S - pad} y2={y(g)} stroke="#1a2233" strokeWidth="1" />
          </g>
        ))}
        <rect x={pad} y={pad} width={inner} height={inner} fill="none" stroke="#26314a" strokeWidth="1" />
        <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#475569" strokeWidth="1.25" strokeDasharray="4 4" />
        {pts.length > 1 && (
          <polyline
            points={pts.map((b) => `${x(b.confidence)},${y(b.frequency)}`).join(" ")}
            fill="none" stroke="#10b981" strokeWidth="1.5" opacity="0.5"
          />
        )}
        {pts.map((b, i) => (
          <circle
            key={i} cx={x(b.confidence)} cy={y(b.frequency)}
            r={active === i ? 4 + (b.n / maxN) * 4 + 2 : 3 + (b.n / maxN) * 4}
            fill="#10b981" stroke={active === i ? "#ffffff" : "#04140d"} strokeWidth={active === i ? 1.5 : 1}
            fillOpacity={active === null || active === i ? 1 : 0.4}
            className="cursor-pointer"
            onClick={() => setActive(active === i ? null : i)}
            onMouseEnter={() => setActive(i)}
          />
        ))}
        <text x={S / 2} y={S - 6} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="600">MODEL SAYS →</text>
        <text x={10} y={S / 2} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="600" transform={`rotate(-90 10 ${S / 2})`}>ACTUALLY HAPPENED →</text>
      </svg>
      <p className="text-[11px] mt-1 min-h-[2.4em] leading-snug">
        {a ? (
          <span className="text-slate-300">
            When the model said about <span className="font-mono text-slate-200">{Math.round(a.confidence * 100)}%</span>, it
            actually happened <span className="font-mono text-slate-200">{Math.round(a.frequency * 100)}%</span> of the time
            <span className="text-slate-500"> (over {a.n} pick{a.n === 1 ? "" : "s"})</span>.
          </span>
        ) : (
          <span className="text-slate-600">Tap a point to compare what the model said with what happened. On the diagonal means the odds matched reality.</span>
        )}
      </p>
    </div>
  )
}
