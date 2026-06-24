"use client"
/**
 * Admin Actions — tail of admin_actions log (dashboard-skill hygiene #1).
 *
 * Reads /admin/admin-actions (or the embedded payload on /overview) and
 * shows the last 50 state-changing POSTs with status colour-coded:
 *   green = ok, amber = pending, rose = error.
 *
 * The operator-side "what changed and when" surface — if a seed/pause
 * fires (intentionally or by misclick) you see it here within one poll.
 */
import { Section, fmtTimeAgo } from "@/components/admin/parts"

interface AdminAction {
  id: number
  action: string
  endpoint: string
  requested_at: string | null
  completed_at: string | null
  status: "pending" | "ok" | "error"
  error: string | null
}

export function AdminActions({ data }: { data: { count: number; items: AdminAction[] } | null }) {
  const items = data?.items ?? []
  return (
    <Section
      title="Admin Actions"
      subtitle={
        items.length === 0
          ? "No state-changing actions yet — every Pause / Seed / Run will appear here"
          : `Last ${items.length} state-changing POSTs (newest first)`
      }
    >
      {items.length === 0 ? (
        <p className="text-[11px] text-slate-600">
          Empty by design — fires the first time you trigger any action from the command palette or a button below.
        </p>
      ) : (
        <div className="border border-edge bg-surface-2 rounded-lg divide-y divide-edge/40 max-h-72 overflow-y-auto">
          {items.map((it) => (
            <Row key={it.id} item={it} />
          ))}
        </div>
      )}
    </Section>
  )
}

function Row({ item }: { item: AdminAction }) {
  const dotColor = item.status === "ok" ? "bg-emerald-400"
    : item.status === "error" ? "bg-rose-400"
    : "bg-amber-400 animate-pulse"
  const textColor = item.status === "error" ? "text-rose-300" : "text-slate-300"
  const duration = (() => {
    if (!item.requested_at || !item.completed_at) return null
    try {
      const ms = new Date(item.completed_at).getTime() - new Date(item.requested_at).getTime()
      if (ms < 1000) return `${ms}ms`
      return `${(ms / 1000).toFixed(1)}s`
    } catch { return null }
  })()
  return (
    <div className="flex items-start gap-3 px-3 py-2 text-[11px]">
      <span className={`w-1.5 h-1.5 rounded-full mt-1.5 shrink-0 ${dotColor}`} />
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className={`font-mono font-bold ${textColor} truncate`}>{item.action}</span>
          {duration && <span className="text-[10px] text-slate-600 font-mono">{duration}</span>}
        </div>
        {item.error && (
          <p className="text-[10px] text-rose-400 mt-0.5 truncate" title={item.error}>{item.error}</p>
        )}
      </div>
      <span className="text-[10px] text-slate-600 font-mono shrink-0 tabular-nums">
        {fmtTimeAgo(item.requested_at)}
      </span>
    </div>
  )
}
