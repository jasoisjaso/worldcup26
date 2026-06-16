import type { RadarTeam } from "@/lib/types"

/** Percentile radar (StatsBomb-style): each axis is the team's 0-100 percentile vs the
 *  48-team field. One team, or two overlaid (solid vs dashed so it reads without colour). */
export function TeamRadar({
  axes, teamA, teamB,
}: { axes: string[]; teamA: RadarTeam; teamB?: RadarTeam }) {
  const S = 260
  const cx = S / 2
  const cy = S / 2 + 6
  const R = 86
  const N = axes.length
  const COL_A = "#34d399" // emerald
  const COL_B = "#fb923c" // orange

  const angle = (k: number) => -Math.PI / 2 + (2 * Math.PI * k) / N
  const point = (k: number, frac: number) => {
    const a = angle(k)
    return [cx + R * frac * Math.cos(a), cy + R * frac * Math.sin(a)] as const
  }
  const poly = (t: RadarTeam) =>
    axes.map((ax, k) => point(k, Math.max(0.02, (t.values[ax] ?? 0) / 100)).join(",")).join(" ")

  return (
    <div>
      <svg viewBox={`0 0 ${S} ${S}`} className="w-full max-w-[320px] mx-auto" role="img"
           aria-label={`Percentile radar for ${teamA.name}${teamB ? ` vs ${teamB.name}` : ""}`}>
        {/* concentric guide rings + spokes */}
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <circle key={f} cx={cx} cy={cy} r={R * f} fill="none" stroke="#1a2233" strokeWidth="1" />
        ))}
        {axes.map((ax, k) => {
          const [x, y] = point(k, 1)
          return <line key={ax} x1={cx} y1={cy} x2={x} y2={y} stroke="#1a2233" strokeWidth="1" />
        })}

        {/* team B first (under) */}
        {teamB && (
          <>
            <polygon points={poly(teamB)} fill={COL_B} fillOpacity="0.16" stroke={COL_B} strokeWidth="1.75" strokeDasharray="4 3" />
            {axes.map((ax, k) => {
              const [x, y] = point(k, Math.max(0.02, (teamB.values[ax] ?? 0) / 100))
              return <circle key={ax} cx={x} cy={y} r="2.5" fill={COL_B} />
            })}
          </>
        )}
        {/* team A */}
        <polygon points={poly(teamA)} fill={COL_A} fillOpacity="0.22" stroke={COL_A} strokeWidth="2" />
        {axes.map((ax, k) => {
          const [x, y] = point(k, Math.max(0.02, (teamA.values[ax] ?? 0) / 100))
          return <circle key={ax} cx={x} cy={y} r="2.8" fill={COL_A} />
        })}

        {/* axis labels just outside the ring */}
        {axes.map((ax, k) => {
          const [x, y] = point(k, 1.22)
          const a = angle(k)
          const anchor = Math.abs(Math.cos(a)) < 0.3 ? "middle" : Math.cos(a) > 0 ? "start" : "end"
          return (
            <text key={ax} x={x} y={y} textAnchor={anchor} dominantBaseline="middle"
                  fill="#9db0d0" fontSize="9" fontWeight="600">{ax}</text>
          )
        })}
      </svg>

      <div className="flex items-center justify-center gap-4 mt-1 text-[11px]">
        <span className="flex items-center gap-1.5">
          <span className="w-3 h-[2px]" style={{ background: COL_A }} />
          <span className="text-slate-300">{teamA.name}</span>
        </span>
        {teamB && (
          <span className="flex items-center gap-1.5">
            <span className="w-3 h-0 border-t-2 border-dashed" style={{ borderColor: COL_B }} />
            <span className="text-slate-300">{teamB.name}</span>
          </span>
        )}
      </div>
      <p className="text-center text-[10px] text-slate-600 mt-1">Percentile vs all 48 teams. Further out is stronger.</p>
    </div>
  )
}
