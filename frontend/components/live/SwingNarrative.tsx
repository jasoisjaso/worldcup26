"use client"
/**
 * Auto-generated narrative for a big WP swing.
 * Surfaces on every live match card when the last sparkline tick is annotated
 * with an event_label like "GOAL — Lainez" or "RED — Pulisic".
 *
 * Pulled the latest tick's event + WP and computes the swing vs the prior tick.
 * Renders nothing when there's been no recent event or swing.
 */
import { useMemo } from "react"

interface Tick { e: number; h: number; a: number; label?: string | null }

interface Props {
  sparkline: Array<{ e: number; h: number; a: number }>
  events: Array<{ elapsed: number; type: string; detail: string; player_name: string | null; team_name: string | null }>
  homeName: string
  awayName: string
}

export function SwingNarrative({ sparkline, events, homeName, awayName }: Props) {
  const insight = useMemo(() => {
    if (!sparkline || sparkline.length < 2) return null

    // Latest two ticks
    const cur = sparkline[sparkline.length - 1]
    const prev = sparkline[sparkline.length - 2]
    if (!cur || !prev) return null

    const homeSwing = cur.h - prev.h
    const awaySwing = cur.a - prev.a
    const maxSwing = Math.max(Math.abs(homeSwing), Math.abs(awaySwing))

    // Don't narrate small noise
    if (maxSwing < 0.08) return null

    // Find the most recent goal/red event near this elapsed minute
    const recentEvent = [...events].reverse().find((e) => {
      if (!e || typeof e.elapsed !== "number") return false
      if (Math.abs(e.elapsed - cur.e) > 5) return false
      return e.type === "Goal" || (e.type === "Card" && e.detail?.includes("Red"))
    })

    const moverName = homeSwing > 0 ? homeName : awayName
    const moverPct = Math.round((homeSwing > 0 ? cur.h : cur.a) * 100)
    const direction = "up"

    let action = "made a key move"
    if (recentEvent) {
      if (recentEvent.type === "Goal") {
        action = `scored${recentEvent.player_name ? ` via ${recentEvent.player_name}` : ""}`
      } else if (recentEvent.detail?.includes("Red")) {
        action = `went down to 10${recentEvent.player_name ? ` (${recentEvent.player_name} sent off)` : ""}`
      }
    }

    return {
      moverName, moverPct, action, direction,
      swingPct: Math.round(maxSwing * 100),
      minute: cur.e,
    }
  }, [sparkline, events, homeName, awayName])

  if (!insight) return null

  const upish = insight.direction === "up"
  return (
    <div className={`px-4 py-2.5 ${upish ? "bg-emerald-500/[0.05] border-y border-emerald-500/15" : "bg-rose-500/[0.05] border-y border-rose-500/15"}`}>
      <p className={`text-[10px] font-bold uppercase tracking-[0.18em] mb-1 ${upish ? "text-emerald-400" : "text-rose-400"}`}>
        What just happened
      </p>
      <p className="text-[13px] text-slate-200 leading-relaxed">
        <span className="font-bold">{insight.moverName}</span> {insight.action} at{" "}
        <span className="font-mono">{insight.minute}'</span>. Win probability swung{" "}
        <span className="font-mono font-bold">{insight.swingPct} points</span> to{" "}
        <span className="font-mono font-bold">{insight.moverPct}%</span>.
      </p>
    </div>
  )
}
