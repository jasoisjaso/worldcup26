import type { TournamentTeam } from "@/lib/types"

/** How often the model has a team still alive at each knockout stage. Horizontal bars on a
 *  shared 0-100% scale, clamped monotonic so sim noise can't widen the funnel. */
export function SurvivalFunnel({ team }: { team: TournamentTeam }) {
  if (team.p_title == null) return null

  // clamp each stage <= the previous so the funnel only narrows
  let cap = team.p_advance ?? 1
  const stages = (
    [
      ["Reach last 32", team.p_advance],
      ["Reach last 16", team.p_r16],
      ["Reach quarters", team.p_quarter],
      ["Reach semis", team.p_semi],
      ["Reach final", team.p_final],
      ["Win the World Cup", team.p_title],
    ] as const
  ).map(([label, v]) => {
    const val = Math.min(v ?? 0, cap)
    cap = val
    return { label, val }
  })

  return (
    <div className="space-y-2">
      {stages.map((s, i) => (
        <div key={s.label} className="flex items-center gap-3">
          <span className="text-[12px] text-slate-400 w-28 sm:w-32 shrink-0">{s.label}</span>
          <div className="flex-1 h-5 rounded bg-emerald-950/40 overflow-hidden min-w-0">
            <div
              className={`h-full rounded ${i === stages.length - 1 ? "bg-amber-400" : "bg-emerald-500"}`}
              style={{ width: `${Math.max(s.val * 100, s.val > 0 ? 1.5 : 0)}%`, opacity: i === stages.length - 1 ? 1 : 0.85 }}
            />
          </div>
          <span className="font-mono tabular-nums text-[12px] font-bold text-slate-100 w-12 text-right shrink-0">
            {s.val >= 0.995 ? "99%+" : s.val < 0.005 ? "<1%" : `${Math.round(s.val * 100)}%`}
          </span>
        </div>
      ))}
      <p className="text-[10px] text-slate-600 pt-1">Chance of still being alive at each stage, across 20,000 tournament simulations.</p>
    </div>
  )
}
