"use client"
/**
 * Live Match Panel — operator's "what's happening right now" tile.
 *
 * One row per active fixture with everything you'd otherwise pull from
 * multiple sources: status (with knockout pill), elapsed, score (+ shootout
 * when applicable), tick freshness (red if stale), push count for the hour,
 * recent events.
 *
 * Used for MD3 simultaneous-fixture days where two matches run at once and
 * you don't want to flick between the public /live page and a tail of the
 * harvester log.
 *
 * Polls the dedicated /admin/live-panel endpoint every 15s.
 */
import { useEffect, useState } from "react"
import { Section, fmt } from "@/components/admin/parts"

interface LiveItem {
  match_id: string
  label: string
  matchday: number | null
  group: string | null
  is_knockout: boolean
  status: string
  elapsed_min: number | null
  home_score: number | null
  away_score: number | null
  shootout_home_score: number | null
  shootout_away_score: number | null
  tick_age_secs: number | null
  stale: boolean
  push_count_1h: number
  recent_events: Array<{
    minute: number
    type: string
    detail: string | null
    player: string | null
    team: string | null
  }>
}

interface LivePanel { count: number; items: LiveItem[] }

const STATUS_LABEL: Record<string, string> = {
  "1H": "1st", "HT": "HT", "2H": "2nd",
  "ET": "ET", "BT": "ET break", "P": "Pens",
  "FT": "FT", "AET": "AET", "PEN": "Pens FT",
  "LIVE": "Live",
}

function fmtTickAge(secs: number | null): string {
  if (secs == null) return "—"
  if (secs < 60) return `${secs}s`
  return `${Math.round(secs / 60)}m`
}

export function LiveMatchPanel({ initial }: { initial: LivePanel | null }) {
  const [data, setData] = useState<LivePanel | null>(initial)

  // Authenticated via the admin cookie that the existing /api/admin/proxy/*
  // routes consume — same flow as the parent dashboard's polling.
  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch("/api/admin/proxy/harvester/live-panel", { cache: "no-store" })
        if (r.ok) setData(await r.json())
      } catch { /* keep stale */ }
    }, 15000)
    return () => clearInterval(iv)
  }, [])

  const items = data?.items ?? []
  const subtitle = items.length === 0
    ? "No matches in play"
    : `${items.length} live · refreshes every 15s`

  return (
    <Section title="Live Matches" subtitle={subtitle}>
      {items.length === 0 ? (
        <p className="text-[11px] text-slate-600">
          Waiting for the next kickoff. Live polling skips API calls when no fixture is plausibly in play.
        </p>
      ) : (
        <div className="space-y-3">
          {items.map((it) => (
            <LiveRow key={it.match_id} item={it} />
          ))}
        </div>
      )}
    </Section>
  )
}

function LiveRow({ item }: { item: LiveItem }) {
  const isShootout = item.status === "P" || item.status === "PEN"
  const statusLabel = STATUS_LABEL[item.status] ?? item.status
  const homePens = item.shootout_home_score
  const awayPens = item.shootout_away_score
  const tickColor = item.stale ? "text-rose-400" : (item.tick_age_secs ?? 0) > 60 ? "text-amber-400" : "text-emerald-400"
  return (
    <div className="border border-edge bg-surface-2 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1.5">
        {item.is_knockout && (
          <span className="text-[8px] font-bold uppercase tracking-widest text-amber-400 border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 rounded">
            KO
          </span>
        )}
        <span className="text-[11px] text-slate-600 font-mono">
          {item.group ? `Grp ${item.group}` : ""} MD{item.matchday ?? "?"}
        </span>
        <span className="text-[11px] font-bold uppercase tracking-widest text-rose-300 ml-auto">{statusLabel}</span>
        <span className="text-[11px] font-mono text-slate-400 tabular-nums w-9 text-right">
          {item.elapsed_min ?? "—"}&apos;
        </span>
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[13px] font-bold text-white truncate flex-1">{item.label.toUpperCase()}</span>
        <span className="font-mono text-[20px] tabular-nums font-black text-white shrink-0">
          {item.home_score ?? 0}–{item.away_score ?? 0}
        </span>
        {isShootout && homePens != null && awayPens != null && (
          <span className="text-[11px] font-mono text-amber-300 tabular-nums shrink-0">
            ({homePens}–{awayPens})
          </span>
        )}
      </div>
      <div className="flex items-center gap-3 text-[10px] font-mono mt-1.5">
        <span className={tickColor}>● tick {fmtTickAge(item.tick_age_secs)} ago</span>
        <span className="text-slate-500">📲 {fmt(item.push_count_1h)} pushes / 1h</span>
      </div>
      {item.recent_events.length > 0 && (
        <div className="mt-2 pt-2 border-t border-edge/40 flex flex-wrap gap-1.5">
          {item.recent_events.map((e, i) => {
            const icon = e.type === "Goal"
              ? (e.detail === "Missed Penalty" ? "🚫"
                  : e.detail === "Own Goal" ? "🅾️" : "⚽")
              : e.type === "Card" ? (e.detail?.includes("Yellow") ? "🟨" : "🟥")
              : e.type === "subst" ? "↔" : "•"
            return (
              <span key={i} className="text-[10px] font-mono text-slate-400 bg-surface-1 border border-edge/40 px-1.5 py-0.5 rounded">
                <span>{icon}</span>
                <span className="text-slate-600 ml-1">{e.minute}&apos;</span>
                <span className="text-slate-300 ml-1 truncate inline-block max-w-[120px] align-bottom">{e.player ?? e.team ?? "—"}</span>
              </span>
            )
          })}
        </div>
      )}
    </div>
  )
}
