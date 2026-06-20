"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"

type Overview = {
  queue: Record<string, number>
  raw_blobs: { total: number; processed: number; unprocessed: number }
  tables: Record<string, number>
  throughput_24h: { completed: number; errors: number }
  last_completed: {
    id: number
    endpoint: string
    completed_at: string | null
    bytes: number | null
  } | null
  last_error: {
    id: number
    endpoint: string | null
    error_type: string | null
    error_msg: string | null
    logged_at: string | null
  } | null
  recent_errors: Array<{
    id: number
    endpoint: string | null
    error_type: string | null
    error_msg: string | null
    logged_at: string | null
  }>
  quota_budget: {
    hours_since_midnight_utc: number
    hours_until_reset: number
    phase: number
    phase_label: string
    quota_remaining: number | null
    daily_calls_made: number
    burn_rate_per_hour: number
    projected_daily_total: number
    projection_alert: "OK" | "TIGHT" | "EXHAUST_RISK"
    backfill_calls_today: number
    harvester_tick: number
    harvester_enabled: boolean
    backfill_allowed: boolean
    harvester_allowed: boolean
    injuries_allowed: boolean
  }
  feeds: {
    feeds: Record<
      string,
      {
        label: string
        last_success: string | null
        age_minutes: number | null
        interval_minutes: number
        stale: boolean
      }
    >
    degraded: string[]
    all_fresh: boolean
  }
  caches: Record<
    string,
    {
      path: string
      exists: boolean
      size_bytes?: number
      age_seconds?: number
      modified_at?: string
      error?: string
    }
  >
  settings: Record<string, { value: string | null; updated_at: string | null }>
  build: { commit: string }
}

const DAILY_QUOTA = 7500

function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

function fmtMinutes(min: number | null | undefined): string {
  if (min == null) return "—"
  if (min < 1) return `${Math.round(min * 60)}s`
  if (min < 60) return `${Math.round(min)}m`
  if (min < 1440) return `${Math.round(min / 60)}h`
  return `${Math.round(min / 1440)}d`
}

function fmtBytes(b: number | null | undefined): string {
  if (b == null) return "—"
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / (1024 * 1024)).toFixed(2)}MB`
}

function fmtTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "never"
  try {
    const t = new Date(iso).getTime()
    const secs = Math.max(0, Math.round((Date.now() - t) / 1000))
    return fmtAge(secs) + " ago"
  } catch {
    return iso
  }
}

export default function AdminDashboard() {
  const router = useRouter()
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [actionBusy, setActionBusy] = useState<string | null>(null)
  const [actionResult, setActionResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/proxy/harvester/overview", { cache: "no-store" })
      if (res.status === 401) {
        router.replace("/admin/login")
        return
      }
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body?.detail ?? body?.error ?? `HTTP ${res.status}`)
        setLoading(false)
        return
      }
      const json = (await res.json()) as Overview
      setData(json)
      setError(null)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }, [router])

  useEffect(() => {
    load()
    const id = setInterval(() => setRefreshTick((t) => t + 1), 30_000)
    return () => clearInterval(id)
  }, [load])

  useEffect(() => {
    if (refreshTick > 0) load()
  }, [refreshTick, load])

  async function callAction(label: string, path: string) {
    setActionBusy(label)
    setActionResult(null)
    try {
      const res = await fetch(`/api/admin/proxy/${path}`, {
        method: "POST",
        cache: "no-store",
      })
      const body = await res.json().catch(() => ({}))
      const msg = typeof body === "object" ? JSON.stringify(body) : String(body)
      setActionResult({ ok: res.ok, msg: msg.slice(0, 300) })
      await load()
    } catch (e) {
      setActionResult({ ok: false, msg: (e as Error).message })
    } finally {
      setActionBusy(null)
    }
  }

  async function signOut() {
    await fetch("/api/admin/auth", { method: "DELETE" })
    router.replace("/admin/login")
  }

  const paused = useMemo(() => {
    if (!data) return null
    return !data.quota_budget.harvester_enabled
  }, [data])

  if (loading) {
    return (
      <div className="p-8 text-slate-400 text-sm">Loading admin overview…</div>
    )
  }

  if (error && !data) {
    return (
      <div className="p-8 text-amber-400 text-sm space-y-2">
        <div>Failed to load: {error}</div>
        <button
          onClick={() => router.replace("/admin/login")}
          className="text-xs text-slate-400 underline"
        >
          Sign in again
        </button>
      </div>
    )
  }

  if (!data) return null

  const q = data.quota_budget
  const quotaPct =
    q.quota_remaining == null ? null : Math.max(0, Math.min(100, (q.quota_remaining / DAILY_QUOTA) * 100))
  const alertColor =
    q.projection_alert === "OK"
      ? "text-emerald-400"
      : q.projection_alert === "TIGHT"
      ? "text-amber-400"
      : "text-red-400"

  return (
    <div className="min-h-screen text-slate-200 p-4 lg:p-8 max-w-7xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between mb-8 gap-4 flex-wrap">
        <div>
          <div className="text-xs uppercase tracking-[0.18em] text-amber-500/80">
            WC26 · Internal admin
          </div>
          <h1 className="font-display text-2xl text-slate-100">
            Harvester · API budget
          </h1>
          <div className="text-xs text-slate-500 mt-1 font-mono">
            build {data.build.commit.slice(0, 8)} · refreshes every 30s · {fmtTimeAgo(new Date().toISOString())}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => load()}
            className="text-xs px-3 py-1.5 border border-edge rounded bg-surface-2 hover:bg-surface-3 transition"
          >
            ↻ Refresh
          </button>
          <button
            onClick={signOut}
            className="text-xs px-3 py-1.5 border border-edge rounded bg-surface-2 hover:bg-surface-3 transition"
          >
            Sign out
          </button>
        </div>
      </header>

      {/* Pause banner */}
      <PauseBanner
        paused={!!paused}
        onToggle={() =>
          callAction(paused ? "resume" : "pause", paused ? "harvester/resume" : "harvester/pause")
        }
        busy={actionBusy === "pause" || actionBusy === "resume"}
      />

      {/* KPI strip */}
      <section className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <Kpi
          label="Quota remaining"
          value={q.quota_remaining == null ? "—" : q.quota_remaining.toLocaleString()}
          sub={quotaPct == null ? "no observation yet" : `${quotaPct.toFixed(0)}% of ${DAILY_QUOTA}`}
          accent={
            q.quota_remaining == null
              ? "neutral"
              : q.quota_remaining < 1000
              ? "danger"
              : q.quota_remaining < 2500
              ? "warn"
              : "ok"
          }
        />
        <Kpi
          label="Calls today"
          value={q.daily_calls_made.toLocaleString()}
          sub={`${q.burn_rate_per_hour}/h burn · projected ${Math.round(
            q.projected_daily_total,
          ).toLocaleString()}`}
          accent={q.projection_alert === "OK" ? "ok" : q.projection_alert === "TIGHT" ? "warn" : "danger"}
        />
        <Kpi
          label="Phase"
          value={`${q.phase} · ${q.phase_label}`}
          sub={`${q.hours_until_reset.toFixed(1)}h until UTC reset`}
          accent="neutral"
        />
        <Kpi
          label="Throughput 24h"
          value={data.throughput_24h.completed.toLocaleString()}
          sub={`${data.throughput_24h.errors} errors`}
          accent={data.throughput_24h.errors > 50 ? "warn" : "ok"}
        />
      </section>

      {/* Quota gauge */}
      <Card title="API budget" subtitle={`Burn projection: ${q.projection_alert}`}>
        <div className="space-y-3">
          <QuotaBar pct={quotaPct} remaining={q.quota_remaining} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Stat label="Harvester allowed" value={q.harvester_allowed ? "yes" : "no"} good={q.harvester_allowed} />
            <Stat label="Backfill allowed" value={q.backfill_allowed ? "yes" : "no"} good={q.backfill_allowed} />
            <Stat label="Injuries allowed" value={q.injuries_allowed ? "yes" : "no"} good={q.injuries_allowed} />
            <Stat label="Harvester enabled" value={q.harvester_enabled ? "yes" : "PAUSED"} good={q.harvester_enabled} />
          </div>
          <div className={`text-sm font-mono ${alertColor}`}>
            {q.projection_alert === "OK" && "On track. Comfortable headroom for the rest of the UTC day."}
            {q.projection_alert === "TIGHT" && `Projected ${Math.round(q.projected_daily_total).toLocaleString()} > 85% of ${DAILY_QUOTA}. Pacing will tighten automatically.`}
            {q.projection_alert === "EXHAUST_RISK" && `Projected ${Math.round(q.projected_daily_total).toLocaleString()} exceeds the daily ${DAILY_QUOTA} quota. Consider pausing the harvester.`}
          </div>
        </div>
      </Card>

      {/* Feed health */}
      <Card
        title={`Feed health · ${data.feeds.all_fresh ? "all fresh" : `${data.feeds.degraded.length} stale`}`}
        subtitle="Scheduler jobs and their last-success age"
      >
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
          {Object.entries(data.feeds.feeds)
            .sort(([, a], [, b]) => (a.stale === b.stale ? 0 : a.stale ? -1 : 1))
            .map(([fid, info]) => (
              <FeedRow key={fid} fid={fid} info={info} />
            ))}
        </div>
      </Card>

      {/* Queue + tables */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card title="Harvest queue" subtitle="Background api-football fetches">
          <div className="grid grid-cols-2 gap-2 mb-3">
            <Stat label="Pending" value={(data.queue.pending ?? 0).toLocaleString()} />
            <Stat label="In progress" value={(data.queue.in_progress ?? 0).toLocaleString()} />
            <Stat label="Done" value={(data.queue.done ?? 0).toLocaleString()} good />
            <Stat label="Error" value={(data.queue.error ?? 0).toLocaleString()} bad={(data.queue.error ?? 0) > 0} />
          </div>
          <div className="text-xs text-slate-500 mb-1">Last completed</div>
          <div className="text-sm font-mono text-slate-300 break-all">
            {data.last_completed
              ? `#${data.last_completed.id} ${data.last_completed.endpoint} · ${fmtBytes(data.last_completed.bytes)} · ${fmtTimeAgo(data.last_completed.completed_at)}`
              : "—"}
          </div>
          <div className="text-xs text-slate-500 mt-3 mb-1">Last error</div>
          <div className="text-sm font-mono text-amber-400/90 break-all">
            {data.last_error
              ? `#${data.last_error.id} ${data.last_error.endpoint ?? "?"} · ${data.last_error.error_type ?? ""} · ${fmtTimeAgo(data.last_error.logged_at)}`
              : "none"}
          </div>
        </Card>

        <Card title="Raw blobs + normalised tables" subtitle="Persistent archive size">
          <div className="grid grid-cols-2 gap-2 mb-3">
            <Stat label="Raw total" value={data.raw_blobs.total.toLocaleString()} />
            <Stat label="Processed" value={data.raw_blobs.processed.toLocaleString()} good />
            <Stat label="Unprocessed" value={data.raw_blobs.unprocessed.toLocaleString()} bad={data.raw_blobs.unprocessed > 100} />
            <Stat label="Player profiles" value={(data.tables.player_profiles ?? 0).toLocaleString()} />
            <Stat label="Player history" value={(data.tables.player_history ?? 0).toLocaleString()} />
            <Stat label="Player season stats" value={(data.tables.player_tournament_stats ?? 0).toLocaleString()} />
            <Stat label="Fixture archive" value={(data.tables.fixture_archives ?? 0).toLocaleString()} />
          </div>
        </Card>
      </div>

      {/* Caches */}
      <Card title="On-disk caches" subtitle="Survives container restarts">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs font-mono">
          {Object.entries(data.caches).map(([name, info]) => (
            <div
              key={name}
              className={`p-3 rounded border ${
                info.exists ? "border-edge bg-surface-2" : "border-amber-500/30 bg-amber-500/5"
              }`}
            >
              <div className="text-slate-400 uppercase tracking-wide mb-1">{name}</div>
              {info.exists ? (
                <div className="space-y-0.5">
                  <div className="text-slate-200">{fmtBytes(info.size_bytes)}</div>
                  <div className="text-slate-500">age {fmtAge(info.age_seconds)}</div>
                  <div className="text-slate-600 text-[10px] truncate">{info.path}</div>
                </div>
              ) : (
                <div className="text-amber-400">missing</div>
              )}
            </div>
          ))}
        </div>
      </Card>

      {/* Recent errors */}
      {data.recent_errors.length > 0 && (
        <Card title="Recent harvest errors" subtitle="Newest first · last 5">
          <div className="space-y-2 text-xs font-mono">
            {data.recent_errors.map((e) => (
              <div
                key={e.id}
                className="p-2 rounded border border-amber-500/20 bg-amber-500/5"
              >
                <div className="flex justify-between mb-1">
                  <span className="text-amber-400">{e.endpoint ?? "?"}</span>
                  <span className="text-slate-500">{fmtTimeAgo(e.logged_at)}</span>
                </div>
                <div className="text-slate-300">{e.error_type ?? ""}</div>
                <div className="text-slate-500 truncate">{e.error_msg ?? ""}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* Manual actions */}
      <Card title="Manual actions" subtitle="Use sparingly — each seed enqueues real api-football work">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
          <ActionButton
            label="Run one tick"
            sub="Force one harvester pass"
            busy={actionBusy === "run-one"}
            onClick={() => callAction("run-one", "harvester/run-one")}
          />
          <ActionButton
            label="Seed WC squads"
            sub="~48 jobs"
            busy={actionBusy === "seed-squads"}
            onClick={() => callAction("seed-squads", "harvester/seed/wc-squads")}
          />
          <ActionButton
            label="Seed full stack"
            sub="WC stats + 2 leagues"
            busy={actionBusy === "seed-full"}
            onClick={() => callAction("seed-full", "harvester/seed/full")}
          />
          <ActionButton
            label="Seed leagues (2)"
            sub="EPL + Bundesliga"
            busy={actionBusy === "seed-leagues"}
            onClick={() => callAction("seed-leagues", "harvester/seed/leagues")}
          />
          <ActionButton
            label="Seed ALL leagues"
            sub="~4,600 jobs · heavy"
            busy={actionBusy === "seed-all"}
            onClick={() => {
              if (confirm("Enqueue ~4,600 fixture jobs across 9 leagues × 2 seasons?")) {
                callAction("seed-all", "harvester/seed/all-leagues")
              }
            }}
            danger
          />
        </div>
        {actionResult && (
          <div
            className={`mt-3 text-xs font-mono p-2 rounded border break-all ${
              actionResult.ok
                ? "border-emerald-500/30 bg-emerald-500/5 text-emerald-300"
                : "border-amber-500/30 bg-amber-500/5 text-amber-300"
            }`}
          >
            {actionResult.msg}
          </div>
        )}
      </Card>
    </div>
  )
}

function PauseBanner({
  paused,
  onToggle,
  busy,
}: {
  paused: boolean
  onToggle: () => void
  busy: boolean
}) {
  return (
    <div
      className={`mb-6 p-3 rounded border flex items-center justify-between gap-3 flex-wrap ${
        paused
          ? "border-amber-500/40 bg-amber-500/10"
          : "border-emerald-500/30 bg-emerald-500/5"
      }`}
    >
      <div>
        <div className={`font-semibold ${paused ? "text-amber-300" : "text-emerald-300"}`}>
          Harvester: {paused ? "PAUSED" : "running"}
        </div>
        <div className="text-xs text-slate-400 mt-0.5">
          {paused
            ? "Background api-football fetches are stopped. Live polling (scores/events) is unaffected."
            : "Background fillers active, throttled by quota gates."}
        </div>
      </div>
      <button
        onClick={onToggle}
        disabled={busy}
        className={`text-xs px-4 py-2 rounded font-semibold transition disabled:opacity-50 ${
          paused
            ? "bg-emerald-500 text-surface-0 hover:bg-emerald-400"
            : "bg-amber-500 text-surface-0 hover:bg-amber-400"
        }`}
      >
        {busy ? "…" : paused ? "Resume" : "Pause"}
      </button>
    </div>
  )
}

function Card({
  title,
  subtitle,
  children,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
}) {
  return (
    <section className="mb-4 border border-edge rounded-lg bg-surface-1 p-4">
      <div className="mb-3">
        <h2 className="text-sm font-semibold text-slate-100">{title}</h2>
        {subtitle && <div className="text-xs text-slate-500 mt-0.5">{subtitle}</div>}
      </div>
      {children}
    </section>
  )
}

function Kpi({
  label,
  value,
  sub,
  accent,
}: {
  label: string
  value: string
  sub: string
  accent: "ok" | "warn" | "danger" | "neutral"
}) {
  const color =
    accent === "ok"
      ? "border-emerald-500/30"
      : accent === "warn"
      ? "border-amber-500/40"
      : accent === "danger"
      ? "border-red-500/50"
      : "border-edge"
  const valColor =
    accent === "ok"
      ? "text-emerald-300"
      : accent === "warn"
      ? "text-amber-300"
      : accent === "danger"
      ? "text-red-400"
      : "text-slate-100"
  return (
    <div className={`p-3 rounded-lg bg-surface-2 border ${color}`}>
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`font-display text-2xl mt-1 ${valColor}`}>{value}</div>
      <div className="text-[11px] text-slate-500 mt-1">{sub}</div>
    </div>
  )
}

function Stat({
  label,
  value,
  good,
  bad,
}: {
  label: string
  value: string | number
  good?: boolean
  bad?: boolean
}) {
  const color = bad ? "text-amber-300" : good ? "text-emerald-300" : "text-slate-200"
  return (
    <div className="p-2 rounded bg-surface-2 border border-edge">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`font-mono ${color}`}>{value}</div>
    </div>
  )
}

function QuotaBar({ pct, remaining }: { pct: number | null; remaining: number | null }) {
  if (pct == null) {
    return (
      <div className="text-xs text-slate-500">
        No quota observation yet — waiting on the live poller's next tick.
      </div>
    )
  }
  const color =
    pct < 15 ? "bg-red-500" : pct < 33 ? "bg-amber-500" : "bg-emerald-500"
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-slate-400 font-mono">
          {remaining?.toLocaleString()} / {DAILY_QUOTA.toLocaleString()}
        </span>
        <span className="text-slate-500">{pct.toFixed(1)}% left</span>
      </div>
      <div className="h-2 bg-surface-3 rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function FeedRow({
  fid,
  info,
}: {
  fid: string
  info: Overview["feeds"]["feeds"][string]
}) {
  const stale = info.stale
  return (
    <div
      className={`p-2 rounded border text-xs flex items-center justify-between gap-2 ${
        stale ? "border-amber-500/40 bg-amber-500/5" : "border-edge bg-surface-2"
      }`}
    >
      <div className="min-w-0">
        <div className="font-mono text-slate-200 truncate">{fid}</div>
        <div className="text-[10px] text-slate-500 truncate">{info.label}</div>
      </div>
      <div className="text-right shrink-0">
        <div className={`font-mono ${stale ? "text-amber-300" : "text-emerald-300"}`}>
          {info.last_success ? fmtMinutes(info.age_minutes) : "—"}
        </div>
        <div className="text-[10px] text-slate-500">every {fmtMinutes(info.interval_minutes)}</div>
      </div>
    </div>
  )
}

function ActionButton({
  label,
  sub,
  onClick,
  busy,
  danger,
}: {
  label: string
  sub: string
  onClick: () => void
  busy: boolean
  danger?: boolean
}) {
  return (
    <button
      onClick={onClick}
      disabled={busy}
      className={`text-left p-3 rounded border transition disabled:opacity-50 ${
        danger
          ? "border-amber-500/40 bg-amber-500/5 hover:bg-amber-500/10"
          : "border-edge bg-surface-2 hover:bg-surface-3"
      }`}
    >
      <div className="text-sm font-semibold text-slate-100">{busy ? "…" : label}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>
    </button>
  )
}
