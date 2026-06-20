"use client"
/** Horizontal scrollable ticker of match events — now with the team flag/abbr
 * prefixed to every event so you can tell at a glance who scored / who was carded.
 *
 * The data already carries `team_name` from MatchEvent; previously we just
 * threw it away. Showing it removes the cognitive load of "wait, which team
 * does that player play for?". */

interface LiveEvent {
  elapsed: number
  extra: number | null
  type: string
  detail: string
  player_name: string | null
  assist_name: string | null
  team_name: string | null
}

interface TickerProps {
  events: LiveEvent[]
  homeName: string
  awayName: string
  homeFlag?: string | null
  awayFlag?: string | null
}

function abbr(name: string): string {
  if (!name) return ""
  // Use first 3 letters of the first word so "Brazil" → "BRA", "Great Britain (England)" → "GRE".
  return name.replace(/[^a-zA-Z ]/g, "").split(/\s+/)[0].slice(0, 3).toUpperCase()
}

export function EventTicker({ events, homeName, awayName, homeFlag, awayFlag }: TickerProps) {
  const items = events.map((e) => {
    const isGoal = e.type === "Goal"
    const isCard = e.type === "Card"
    if (!isGoal && !isCard) return null
    const icon = isGoal ? "⚽" : e.detail?.includes("Yellow") ? "🟨" : "🟥"
    const minute = e.elapsed + (e.extra ?? 0)
    const isHome = !!(e.team_name && (e.team_name === homeName || homeName.startsWith(e.team_name) || e.team_name.startsWith(homeName)))
    const isAway = !!(e.team_name && (e.team_name === awayName || awayName.startsWith(e.team_name) || e.team_name.startsWith(awayName)))
    const teamLabel = isHome ? abbr(homeName) : isAway ? abbr(awayName) : abbr(e.team_name || "")
    const teamFlag = isHome ? homeFlag : isAway ? awayFlag : null
    let text = e.player_name || ""
    if (isGoal && e.assist_name) text += ` (assist: ${e.assist_name})`
    return { icon, text, isGoal, teamLabel, teamFlag, minute, isHome, isAway }
  }).filter(Boolean) as Array<{ icon: string; text: string; isGoal: boolean; teamLabel: string; teamFlag: string | null | undefined; minute: number; isHome: boolean; isAway: boolean }>

  if (items.length === 0) return null

  return (
    <div className="px-4 py-2 border-b border-edge/20 overflow-x-auto scrollbar-none">
      <div className="flex gap-2">
        {items.map((it, i) => (
          <div
            key={i}
            className={`shrink-0 flex items-center gap-1.5 pl-1.5 pr-2 py-1 rounded-md text-[11px] font-mono tabular-nums border ${
              it.isGoal
                ? "bg-amber-500/10 text-amber-200 border-amber-500/30"
                : "bg-slate-500/10 text-slate-300 border-slate-500/20"
            }`}
            title={`${it.teamLabel} ${it.minute}' ${it.text}`}
          >
            <span>{it.icon}</span>
            <span className="text-slate-500 font-mono">{it.minute}&apos;</span>
            {it.teamFlag ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={it.teamFlag} alt={it.teamLabel} className="w-3.5 h-2.5 rounded-[1px] object-cover" />
            ) : (
              <span className="text-[9px] font-bold opacity-70">{it.teamLabel}</span>
            )}
            <span className="font-sans font-semibold text-white">{it.text}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
