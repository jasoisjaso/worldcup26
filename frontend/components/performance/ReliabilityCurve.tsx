import type { ReliabilityBin } from "@/lib/types"

/** Calibration plot: where the dots sit on the diagonal, the stated probabilities match
 *  reality. Above the line = the model was too cautious; below = overconfident. */
export function ReliabilityCurve({ bins }: { bins: ReliabilityBin[] }) {
  const S = 240
  const pad = 28
  const inner = S - pad * 2
  const x = (v: number) => pad + v * inner
  const y = (v: number) => pad + (1 - v) * inner
  const pts = bins.filter((b) => b.n > 0)
  const maxN = Math.max(1, ...pts.map((b) => b.n))

  return (
    <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[300px] mx-auto" role="img" aria-label="Calibration reliability curve">
      {/* grid */}
      {[0.25, 0.5, 0.75].map((g) => (
        <g key={g}>
          <line x1={x(g)} y1={pad} x2={x(g)} y2={S - pad} stroke="#1a2233" strokeWidth="1" />
          <line x1={pad} y1={y(g)} x2={S - pad} y2={y(g)} stroke="#1a2233" strokeWidth="1" />
        </g>
      ))}
      {/* axes box */}
      <rect x={pad} y={pad} width={inner} height={inner} fill="none" stroke="#26314a" strokeWidth="1" />
      {/* perfect-calibration diagonal */}
      <line x1={x(0)} y1={y(0)} x2={x(1)} y2={y(1)} stroke="#475569" strokeWidth="1.25" strokeDasharray="4 4" />
      {/* connecting path */}
      {pts.length > 1 && (
        <polyline
          points={pts.map((b) => `${x(b.confidence)},${y(b.frequency)}`).join(" ")}
          fill="none"
          stroke="#ffb000"
          strokeWidth="1.5"
          opacity="0.5"
        />
      )}
      {/* points sized by sample count */}
      {pts.map((b, i) => (
        <circle
          key={i}
          cx={x(b.confidence)}
          cy={y(b.frequency)}
          r={3 + (b.n / maxN) * 4}
          fill="#ffb000"
          stroke="#06120c"
          strokeWidth="1"
        />
      ))}
      {/* labels */}
      <text x={S / 2} y={S - 6} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="600">
        MODEL SAYS →
      </text>
      <text x={10} y={S / 2} textAnchor="middle" fill="#64748b" fontSize="9" fontWeight="600" transform={`rotate(-90 10 ${S / 2})`}>
        ACTUALLY HAPPENED →
      </text>
    </svg>
  )
}
