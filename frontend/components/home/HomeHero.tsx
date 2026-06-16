import type { TournamentProjection, HistoryStats } from "@/lib/types"

function Flag({ url, color }: { url?: string; color?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className="w-5 h-[15px] rounded-[2px] object-cover ring-1 ring-white/10 shrink-0" />
  }
  return <span className="w-5 h-[15px] rounded-[2px] shrink-0 ring-1 ring-white/10" style={{ background: color || "#1e293b" }} />
}

export function HomeHero({ proj, stats }: { proj: TournamentProjection | null; stats: HistoryStats | null }) {
  const hasTitle = !!proj?.has_knockout && proj.teams.some((t) => t.p_title != null)
  const top = proj?.teams ?? []
  const metric = (t: (typeof top)[number]) => (hasTitle ? (t.p_title ?? 0) : t.p_advance)
  const sorted = [...top].sort((a, b) => metric(b) - metric(a)).slice(0, 3)

  const liveTracked = stats && stats.total > 0
  const trustLine = liveTracked
    ? `Tracked over ${stats!.total} settled pick${stats!.total === 1 ? "" : "s"}`
    : "Validated on ~1,500 internationals"

  return (
    <div className="relative overflow-hidden rounded-2xl border border-emerald-500/15 bg-gradient-to-br from-[#0c1512] to-[#0a0f18] p-4 sm:p-5">
      <div className="absolute -right-16 -top-16 w-48 h-48 rounded-full bg-emerald-500/[0.07] blur-3xl pointer-events-none" />
      <div className="relative flex flex-col lg:flex-row gap-4 lg:items-center">
        {/* contender mini-board */}
        <div className="flex-1 min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">The model's call</p>
          <h2 className="text-[19px] sm:text-[22px] font-black tracking-tight text-white leading-tight mt-0.5 mb-3">
            {hasTitle ? "Who wins the World Cup?" : "Who reaches the knockouts?"}
          </h2>
          {sorted.length > 0 ? (
            <div className="space-y-1.5 max-w-md">
              {sorted.map((t, i) => {
                const v = metric(t)
                const color = t.primary_color && t.primary_color !== "#ffffff" ? t.primary_color : "#10b981"
                return (
                  <div key={t.code} className="flex items-center gap-2.5">
                    <span className="font-mono text-[11px] text-slate-600 w-3">{i + 1}</span>
                    <Flag url={t.flag_url} color={t.primary_color} />
                    <span className="text-[13px] font-semibold text-slate-100 w-24 sm:w-28 truncate">{t.name}</span>
                    <div className="flex-1 h-2 rounded-full bg-white/[0.05] overflow-hidden min-w-0">
                      <div className="h-full rounded-full" style={{ width: `${Math.min(100, Math.max(0, v * 100))}%`, background: color, opacity: 0.85 }} />
                    </div>
                    <span className="font-mono text-[12px] tabular-nums font-bold text-slate-200 w-9 text-right">
                      {Math.round(v * 100)}%
                    </span>
                  </div>
                )
              })}
            </div>
          ) : (
            <p className="text-[12px] text-slate-500">Projections warming up…</p>
          )}
          <a href="/winner" className="inline-block mt-3 text-[12px] font-semibold text-emerald-400 hover:underline">
            Full projections →
          </a>
        </div>

        {/* trust strip */}
        <a
          href="/performance"
          className="lg:w-[210px] shrink-0 rounded-xl border border-[#16203a] bg-[#0a0f18]/70 p-3.5 hover:border-emerald-500/30 transition-colors group"
        >
          <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500 mb-1.5">The model, graded</p>
          {liveTracked ? (
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[22px] tabular-nums font-bold text-white">
                {Math.round((stats!.accuracy ?? 0) * 100)}%
              </span>
              <span className="text-[11px] text-slate-500">pick hit rate</span>
            </div>
          ) : (
            <div className="flex items-baseline gap-2">
              <span className="font-mono text-[22px] tabular-nums font-bold text-white">0.17</span>
              <span className="text-[11px] text-slate-500">backtest RPS</span>
            </div>
          )}
          <p className="text-[11px] text-slate-500 mt-1.5 leading-snug">{trustLine}.</p>
          <p className="text-[12px] font-semibold text-emerald-400 mt-2 group-hover:underline">See the report card →</p>
        </a>
      </div>
    </div>
  )
}
