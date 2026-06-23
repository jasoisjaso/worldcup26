"use client"
/**
 * ShootoutTracker — penalty shootout visualisation that renders only when
 * a knockout match's status is "P" (shootout in progress) or "PEN" (decided).
 *
 * Layout converged from how Sofascore, FotMob, ESPN and Apple Sports present
 * shootouts on their live pages (researched 2026-06-23):
 *   - Big aggregate score on top: "1-1 (4-3 pens)"
 *   - One dot row per team, left-to-right, one circle per kick
 *     ● filled = scored, ✕ in circle = missed, ◌ pulsing = next kicker pending
 *   - Optional per-kick log below for "who took it" context
 *
 * We derive the dot rows from the persisted MatchEvent rows (type="Goal" with
 * detail="Penalty" or "Missed Penalty", filtered to shootout context via
 * elapsed > 120 OR comments containing "Shootout"). That gives us scored/
 * missed per kick in chronological order; we split by team and render.
 */

interface ShootoutEvent {
  elapsed: number
  extra: number | null
  type: string
  detail: string
  player_name: string | null
  team_name: string | null
  comments?: string | null
}

interface ShootoutTrackerProps {
  homeName: string
  awayName: string
  homeFlag: string | null
  awayFlag: string | null
  shootoutHomeScore: number | null
  shootoutAwayScore: number | null
  regulationHome: number
  regulationAway: number
  events: ShootoutEvent[]
  status: string  // "P" (in progress) or "PEN" (decided)
}

interface KickRow {
  scored: boolean
  player: string | null
}

function isShootoutEvent(e: ShootoutEvent): boolean {
  if (e.type !== "Goal") return false
  if (e.detail !== "Penalty" && e.detail !== "Missed Penalty") return false
  const commentSays = (e.comments || "").toLowerCase().includes("shootout")
  const minute = (e.elapsed || 0) + (e.extra || 0)
  return commentSays || minute > 120
}

function splitKicks(events: ShootoutEvent[], homeName: string, awayName: string): { home: KickRow[]; away: KickRow[] } {
  const isSide = (e: ShootoutEvent, name: string): boolean =>
    !!e.team_name && (e.team_name === name || name.startsWith(e.team_name) || e.team_name.startsWith(name))

  const home: KickRow[] = []
  const away: KickRow[] = []
  for (const e of events) {
    if (!isShootoutEvent(e)) continue
    const row: KickRow = { scored: e.detail === "Penalty", player: e.player_name }
    if (isSide(e, homeName)) home.push(row)
    else if (isSide(e, awayName)) away.push(row)
  }
  return { home, away }
}

function Dot({ kick, pending }: { kick?: KickRow; pending?: boolean }) {
  if (pending) {
    return (
      <span
        className="inline-block w-3.5 h-3.5 rounded-full border border-slate-600 bg-transparent animate-pulse"
        aria-label="next kick pending"
      />
    )
  }
  if (!kick) {
    return (
      <span
        className="inline-block w-3.5 h-3.5 rounded-full border border-slate-700/60 bg-transparent"
        aria-label="not taken"
      />
    )
  }
  if (kick.scored) {
    return (
      <span
        title={kick.player ? `${kick.player} — scored` : "scored"}
        className="inline-block w-3.5 h-3.5 rounded-full bg-emerald-500 ring-1 ring-emerald-300/40"
        aria-label="scored"
      />
    )
  }
  return (
    <span
      title={kick.player ? `${kick.player} — missed` : "missed"}
      className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full bg-rose-500/20 border border-rose-400 text-rose-300 text-[10px] font-black leading-none"
      aria-label="missed"
    >
      ×
    </span>
  )
}

function DotRow({ kicks, isUpNext }: { kicks: KickRow[]; isUpNext: boolean }) {
  // Render at least 5 slots so the eye can read "best of 5". Add an extra
  // "pending" dot for the next kicker only on the team that's up. Beyond 5
  // shows sudden-death dots one per actual kick.
  const minSlots = 5
  const filled = kicks.length
  const slots = Math.max(minSlots, filled + (isUpNext ? 1 : 0))
  const dots: React.ReactNode[] = []
  for (let i = 0; i < slots; i++) {
    if (i < filled) dots.push(<Dot key={i} kick={kicks[i]} />)
    else if (i === filled && isUpNext) dots.push(<Dot key={i} pending />)
    else dots.push(<Dot key={i} />)
  }
  return <div className="flex items-center gap-1.5">{dots}</div>
}

export function ShootoutTracker({
  homeName, awayName, homeFlag, awayFlag,
  shootoutHomeScore, shootoutAwayScore,
  regulationHome, regulationAway,
  events, status,
}: ShootoutTrackerProps) {
  const { home, away } = splitKicks(events, homeName, awayName)
  const homeTotal = shootoutHomeScore ?? home.filter(k => k.scored).length
  const awayTotal = shootoutAwayScore ?? away.filter(k => k.scored).length
  // Whose kick is next? Whoever has taken FEWER kicks goes next. If equal,
  // away kicked second so it's home's turn. Only show "up next" while shootout
  // is still live (status="P"); once status="PEN" the shootout is decided.
  const isLive = status === "P"
  const homeUpNext = isLive && (home.length <= away.length)
  const awayUpNext = isLive && (away.length < home.length)
  const decidedLabel = status === "PEN" ? "Decided on penalties" : "Penalty shootout"

  return (
    <div className="px-4 py-3 border-b border-edge/20 bg-gradient-to-br from-amber-500/[0.04] to-transparent">
      <div className="flex items-center gap-2 mb-3">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-300">
          {decidedLabel}
        </p>
        <p className="text-[10px] font-mono tabular-nums text-slate-400 ml-auto">
          {regulationHome}–{regulationAway} after ET · {homeTotal}–{awayTotal} pens
        </p>
      </div>
      <div className="space-y-2.5">
        {/* Home row */}
        <div className="flex items-center gap-3">
          {homeFlag && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={homeFlag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
          )}
          <span className="text-[12px] font-semibold text-slate-200 truncate w-24">{homeName}</span>
          <DotRow kicks={home} isUpNext={homeUpNext} />
          <span className="font-mono text-[16px] tabular-nums font-black text-white ml-auto shrink-0">
            {homeTotal}
          </span>
        </div>
        {/* Away row */}
        <div className="flex items-center gap-3">
          {awayFlag && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={awayFlag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
          )}
          <span className="text-[12px] font-semibold text-slate-200 truncate w-24">{awayName}</span>
          <DotRow kicks={away} isUpNext={awayUpNext} />
          <span className="font-mono text-[16px] tabular-nums font-black text-white ml-auto shrink-0">
            {awayTotal}
          </span>
        </div>
      </div>
      {/* Per-kick log — collapsed by default. Shows kicker name + outcome per
          kick, alternating teams in chronological order. */}
      {(home.length + away.length) > 0 && (
        <details className="mt-3 group">
          <summary className="text-[10px] uppercase tracking-widest text-slate-500 cursor-pointer hover:text-slate-300 select-none list-none flex items-center gap-1">
            <span className="group-open:rotate-90 transition-transform inline-block w-2 text-center">›</span>
            <span>Per-kick log</span>
          </summary>
          <ul className="mt-2 space-y-1 pl-3">
            {interleave(home, away).map((entry, i) => (
              <li key={i} className="flex items-center gap-2 text-[11px]">
                <span className="font-mono tabular-nums text-slate-600 w-5 text-right">{i + 1}</span>
                <span className="text-slate-500 w-12 truncate">{entry.side === "home" ? homeName : awayName}</span>
                <span className={entry.kick.scored ? "text-emerald-400" : "text-rose-400"}>
                  {entry.kick.scored ? "✓" : "✗"}
                </span>
                <span className="text-slate-300 truncate">{entry.kick.player || "?"}</span>
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  )
}

function interleave(home: KickRow[], away: KickRow[]): Array<{ side: "home" | "away"; kick: KickRow }> {
  const out: Array<{ side: "home" | "away"; kick: KickRow }> = []
  const n = Math.max(home.length, away.length)
  for (let i = 0; i < n; i++) {
    if (i < home.length) out.push({ side: "home", kick: home[i] })
    if (i < away.length) out.push({ side: "away", kick: away[i] })
  }
  return out
}
