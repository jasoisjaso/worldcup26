import type { MatchPrediction, Team } from "@/lib/types"

/**
 * "How the tie is decided" — knockout-only. Turns the model's regulation grid
 * into P(settled in 90'), P(extra time), P(penalties), plus each side's overall
 * chance of ADVANCING (regulation + ET + shootout combined). Renders nothing on
 * group games (prediction.knockout is null there).
 */
export function KnockoutResolution({
  knockout,
  home,
  away,
}: {
  knockout: NonNullable<MatchPrediction["knockout"]>
  home: Team
  away: Team
}) {
  const pct = (v: number) => Math.round(v * 100)
  const reg = pct(knockout.decided_in_90)
  const et = pct(knockout.decided_in_et)
  const pens = pct(knockout.penalties)
  const homeAdv = pct(knockout.home_advance)
  const awayAdv = pct(knockout.away_advance)

  // The three phases the tie can be settled in. Widths come straight off the
  // model so they always sum to ~100%.
  const phases = [
    { label: "In 90'", value: reg, cls: "bg-emerald-500", text: "text-emerald-300" },
    { label: "Extra time", value: et, cls: "bg-amber-500", text: "text-amber-300" },
    { label: "Penalties", value: pens, cls: "bg-sky-500", text: "text-sky-300" },
  ]

  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-4">
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
          How the tie is decided
        </p>
        <span className="text-[10px] text-slate-600">
          {pct(knockout.extra_time)}% chance of extra time
        </span>
      </div>

      {/* Phase split bar */}
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-surface-1">
        {phases.map((p) => (
          <div key={p.label} className={p.cls} style={{ width: `${p.value}%` }} title={`${p.label}: ${p.value}%`} />
        ))}
      </div>
      <div className="mt-2 grid grid-cols-3 gap-2">
        {phases.map((p) => (
          <div key={p.label} className="text-center">
            <p className={`text-[17px] font-black tabular-nums leading-none ${p.text}`}>{p.value}%</p>
            <p className="text-[10px] text-slate-500 mt-0.5">{p.label}</p>
          </div>
        ))}
      </div>

      {/* Who advances */}
      <div className="mt-4 pt-3 border-t border-edge">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">
          To advance
        </p>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-2 min-w-0">
            {home.flag_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={home.flag_url} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
            )}
            <span className="text-[12px] font-semibold text-slate-200 truncate">{home.name}</span>
            <span className="text-[14px] font-black text-emerald-400 tabular-nums">{homeAdv}%</span>
          </div>
          <div className="flex-1 h-2 rounded-full overflow-hidden bg-orange-500/70 flex">
            <div className="bg-emerald-500" style={{ width: `${homeAdv}%` }} />
          </div>
          <div className="flex items-center gap-2 min-w-0 justify-end">
            <span className="text-[14px] font-black text-orange-400 tabular-nums">{awayAdv}%</span>
            <span className="text-[12px] font-semibold text-slate-200 truncate">{away.name}</span>
            {away.flag_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={away.flag_url} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
            )}
          </div>
        </div>
      </div>

      <p className="text-[10px] text-slate-600 mt-3 leading-snug">
        Model-derived from the score grid: a tie level after 90&apos; goes to extra time,
        then penalties. &ldquo;To advance&rdquo; combines all three.
      </p>
    </div>
  )
}
