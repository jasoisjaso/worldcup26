/**
 * Golden Boot Watch — leading scorers at WC2026.
 *
 * Cached server-side on an hourly refresh. We render the top 10 with name, country
 * flag-via-photo, goals, assists. Renders nothing when no goals have been scored
 * yet — pre-tournament gracefulness.
 */

interface ScorerRow {
  player_id: number
  name: string
  firstname?: string
  lastname?: string
  nationality?: string
  photo?: string
  team_name?: string
  team_logo?: string
  goals: number
  assists: number
  appearances: number
  minutes: number
  yellow_cards: number
  red_cards: number
}

interface GoldenBootData {
  fetched_at: string | null
  leaderboard: ScorerRow[]
}

export function GoldenBoot({ data }: { data: GoldenBootData | null }) {
  if (!data || data.leaderboard.length === 0) return null
  const top = data.leaderboard.slice(0, 10)
  const leader = top[0]
  const fetched = data.fetched_at ? new Date(data.fetched_at) : null

  return (
    <div className="rounded-2xl border border-amber-500/30 bg-gradient-to-br from-amber-500/[0.06] to-surface-2 shadow-glow-gold overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 flex items-center justify-between border-b border-amber-500/20">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-400">
          ⚽︎ Golden Boot watch
        </p>
        {fetched && (
          <span className="text-[10px] text-slate-600 font-mono">
            updated {fetched.toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit" })}
          </span>
        )}
      </div>

      {/* Hero leader */}
      <div className="px-4 py-3 flex items-center gap-3 border-b border-amber-500/10">
        {leader.photo && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={leader.photo} alt="" className="w-14 h-14 rounded-full ring-2 ring-amber-500/50 object-cover" />
        )}
        <div className="flex-1 min-w-0">
          <p className="text-[16px] font-bold text-white truncate">{leader.name}</p>
          <p className="text-[11px] text-slate-400 truncate">
            {leader.nationality} {leader.team_name && `· ${leader.team_name}`}
          </p>
          <p className="text-[10px] text-slate-500">
            {leader.appearances} app · {Math.round((leader.minutes || 0) / 90)} 90s
          </p>
        </div>
        <div className="text-right shrink-0">
          <p className="font-mono text-[36px] font-black text-amber-400 leading-none tabular-nums">
            {leader.goals}
          </p>
          <p className="text-[9px] text-slate-500 uppercase tracking-wider">goals</p>
        </div>
      </div>

      {/* Chasing pack */}
      <div className="divide-y divide-edge/30">
        {top.slice(1).map((p, i) => (
          <div key={p.player_id} className="px-4 py-2 flex items-center gap-2.5">
            <span className="font-mono text-[11px] text-slate-600 w-4 text-center">{i + 2}</span>
            {p.photo ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={p.photo} alt="" className="w-7 h-7 rounded-full ring-1 ring-white/10 object-cover shrink-0" />
            ) : (
              <span className="w-7 h-7 rounded-full bg-surface-1 shrink-0" />
            )}
            <div className="flex-1 min-w-0">
              <p className="text-[12px] font-semibold text-slate-100 truncate">{p.name}</p>
              <p className="text-[10px] text-slate-500 truncate">{p.nationality}</p>
            </div>
            <p className="font-mono text-[14px] font-bold text-amber-400 tabular-nums w-6 text-right shrink-0">
              {p.goals}
            </p>
            {p.assists > 0 && (
              <p className="font-mono text-[10px] text-slate-500 tabular-nums w-6 text-right shrink-0">
                +{p.assists}a
              </p>
            )}
          </div>
        ))}
      </div>

      <p className="px-4 py-2 text-[10px] text-slate-600 border-t border-edge/40">
        Goals scored at WC2026. Updated after every match. Race re-opens every group day.
      </p>
    </div>
  )
}
