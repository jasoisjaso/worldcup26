/**
 * Head-to-Head historical record between this match's two teams.
 *
 * Shows the all-time record from our home team's perspective and lists the last 5
 * meetings with scoreline + competition + venue. Renders nothing when there's no
 * historical data available.
 */

interface H2HMatch {
  date: string
  competition?: string | null
  season?: number | null
  venue?: string | null
  home_name: string
  away_name: string
  home_goals: number
  away_goals: number
}

interface H2HData {
  home_code: string
  away_code: string
  total_meetings: number
  our_wins: number
  opp_wins: number
  draws: number
  matches: H2HMatch[]
}

function fmtDate(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("en-AU", { year: "numeric", month: "short", day: "numeric" })
  } catch {
    return iso.slice(0, 10)
  }
}

export function HeadToHead({
  data,
  homeName,
  awayName,
}: {
  data: H2HData | null
  homeName: string
  awayName: string
}) {
  if (!data || data.total_meetings === 0) return null

  const summary = [
    { label: homeName, value: data.our_wins, color: "text-emerald-400" },
    { label: "Draw", value: data.draws, color: "text-slate-400" },
    { label: awayName, value: data.opp_wins, color: "text-orange-400" },
  ]
  const recent = data.matches.slice(0, 5)

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 border-b border-edge/40">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
          When they&apos;ve met
        </p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {data.total_meetings} meeting{data.total_meetings === 1 ? "" : "s"} on record
        </p>
      </div>

      {/* Head-to-head pie/strip */}
      <div className="px-4 py-3 grid grid-cols-3 gap-1.5 text-center">
        {summary.map((s) => (
          <div key={s.label}>
            <p className={`font-mono text-[26px] tabular-nums font-black leading-none ${s.color}`}>
              {s.value}
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5 truncate">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Stacked bar */}
      <div className="px-4 pb-3">
        <div className="flex h-1.5 rounded-full overflow-hidden bg-surface-1">
          {summary.map((s, i) => {
            const total = summary.reduce((acc, r) => acc + r.value, 0)
            const pct = total > 0 ? (s.value / total) * 100 : 0
            const bg = i === 0 ? "#10b981" : i === 1 ? "#475569" : "#fb923c"
            return <div key={i} style={{ width: `${pct}%`, background: bg }} />
          })}
        </div>
      </div>

      {/* Last meetings list */}
      {recent.length > 0 && (
        <div className="border-t border-edge/40">
          <p className="px-4 py-2 text-[9px] font-bold uppercase tracking-wider text-slate-600">
            Recent meetings
          </p>
          <div className="divide-y divide-edge/30">
            {recent.map((m, i) => {
              const winner =
                m.home_goals > m.away_goals
                  ? m.home_name
                  : m.away_goals > m.home_goals
                    ? m.away_name
                    : null
              return (
                <div key={i} className="px-4 py-2 flex items-center gap-3 text-[11px]">
                  <span className="text-slate-500 font-mono shrink-0 w-20">
                    {fmtDate(m.date)}
                  </span>
                  <span className="text-slate-300 truncate flex-1">
                    <span className={winner === m.home_name ? "font-bold text-white" : ""}>{m.home_name}</span>
                    <span className="text-slate-500 mx-1">vs</span>
                    <span className={winner === m.away_name ? "font-bold text-white" : ""}>{m.away_name}</span>
                  </span>
                  <span className="font-mono tabular-nums text-slate-100 shrink-0">
                    {m.home_goals}–{m.away_goals}
                  </span>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {recent[0]?.competition && (
        <p className="px-4 py-2 text-[10px] text-slate-600 border-t border-edge/40">
          Source: api-football
        </p>
      )}
    </div>
  )
}
