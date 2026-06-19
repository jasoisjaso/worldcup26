"use client"
/** Horizontal scrollable ticker — goals (who scored + assist) and cards. */

interface LiveEvent {
  elapsed: number; extra: number | null; type: string; detail: string
  player_name: string | null; assist_name: string | null; team_name: string | null
}

export function EventTicker({ events, homeName, awayName }: {
  events: LiveEvent[]; homeName: string; awayName: string
}) {
  const items = events.map((e) => {
    const isGoal = e.type === "Goal"
    const isCard = e.type === "Card"
    if (!isGoal && !isCard) return null
    const icon = isGoal ? "⚽" : e.detail?.includes("Yellow") ? "🟨" : "🟥"
    const minute = e.elapsed + (e.extra ?? 0)
    let text = `${minute}' `
    if (e.player_name) text += e.player_name
    if (isGoal && e.assist_name) text += ` (${e.assist_name})`
    return { icon, text, isGoal }
  }).filter(Boolean) as Array<{ icon: string; text: string; isGoal: boolean }>

  if (items.length === 0) return null

  return (
    <div className="px-4 py-2 border-b border-edge/20 overflow-x-auto scrollbar-none">
      <div className="flex gap-2">
        {items.map((it, i) => (
          <div key={i} className={`shrink-0 px-2 py-1 rounded-md text-[10px] font-mono tabular-nums ${it.isGoal ? "bg-amber-500/10 text-amber-300 border border-amber-500/20" : "bg-slate-500/10 text-slate-300 border border-slate-500/20"}`}>
            {it.icon} {it.text}
          </div>
        ))}
      </div>
    </div>
  )
}
