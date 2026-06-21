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
    per_minute_remaining: number | null
    live_reserve_floor: number
    burn_buffer: number
    burn_window_minutes: number
    daily_calls_made: number
    daily_quota: number
    burn_rate_per_hour: number
    projected_daily_total: number
    projection_alert: "OK" | "TIGHT" | "EXHAUST_RISK"
    backfill_calls_today: number
    harvester_tick: number
    harvester_enabled: boolean
    backfill_allowed: boolean
    harvester_allowed: boolean
    burn_should_fire: boolean
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
  inventory: {
    coverage: Array<{
      key: string
      label: string
      have: number
      target: number | null
      unit: string
    }>
    endpoint_breakdown: Array<{
      endpoint: string
      done: number
      avg_bytes: number
      last_done: string | null
    }>
    activity_7d: Array<{ date: string; completed: number }>
    archive_bytes: number
  }
  sharp_odds: {
    feature_enabled: boolean
    fetched_at: number | null
    age_seconds: number | null
    event_count: number
    sample: {
      event_id: string
      start_time: string | null
      home_name: string
      away_name: string
      pinnacle: Record<string, number>
    } | null
  }
  settings: Record<string, { value: string | null; updated_at: string | null }>
  build: { commit: string }
}

const DAILY_QUOTA_FALLBACK = 7500   // backend now sends quota_budget.daily_quota

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
  const dailyQuota = q.daily_quota ?? DAILY_QUOTA_FALLBACK
  const quotaPct =
    q.quota_remaining == null ? null : Math.max(0, Math.min(100, (q.quota_remaining / dailyQuota) * 100))
  const reservePct = Math.max(0, Math.min(100, (q.live_reserve_floor / dailyQuota) * 100))
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
          sub={quotaPct == null ? "no observation yet" : `${quotaPct.toFixed(0)}% of ${dailyQuota}`}
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

      {/* Data inventory — what we OWN, not just what's queued */}
      <InventoryCard inv={data.inventory} />

      {/* Sharp odds (Pinnacle via SportsGameOdds) — proves the model has a
          calibrated sharp anchor for the blend, not just soft books */}
      <SharpOddsCard so={data.sharp_odds} />

      {/* Quota gauge */}
      <Card title="API budget" subtitle={`Burn projection: ${q.projection_alert}`}>
        <div className="space-y-3">
          <QuotaBar
            pct={quotaPct}
            remaining={q.quota_remaining}
            dailyQuota={dailyQuota}
            reservePct={reservePct}
            reserveFloor={q.live_reserve_floor}
          />
          <PerMinuteBar value={q.per_minute_remaining} burning={q.burn_should_fire} />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <Stat label="Harvester allowed" value={q.harvester_allowed ? "yes" : "no"} good={q.harvester_allowed} />
            <Stat label="Backfill allowed" value={q.backfill_allowed ? "yes" : "no"} good={q.backfill_allowed} />
            <Stat label="Injuries allowed" value={q.injuries_allowed ? "yes" : "no"} good={q.injuries_allowed} />
            <Stat label="Harvester enabled" value={q.harvester_enabled ? "yes" : "PAUSED"} good={q.harvester_enabled} />
          </div>
          <div className={`text-sm font-mono ${alertColor}`}>
            {q.projection_alert === "OK" && "On track. Comfortable headroom for the rest of the UTC day."}
            {q.projection_alert === "TIGHT" && `Projected ${Math.round(q.projected_daily_total).toLocaleString()} > 85% of ${dailyQuota}. Pacing will tighten automatically.`}
            {q.projection_alert === "EXHAUST_RISK" && `Projected ${Math.round(q.projected_daily_total).toLocaleString()} exceeds the daily ${dailyQuota} quota. Consider pausing the harvester.`}
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

function QuotaBar({
  pct,
  remaining,
  dailyQuota,
  reservePct,
  reserveFloor,
}: {
  pct: number | null
  remaining: number | null
  dailyQuota: number
  reservePct: number
  reserveFloor: number
}) {
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
          {remaining?.toLocaleString()} / {dailyQuota.toLocaleString()}
        </span>
        <span className="text-slate-500">{pct.toFixed(1)}% left</span>
      </div>
      <div className="relative h-2 bg-surface-3 rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
        {/* Reserve-floor marker — a vertical tick at LIVE_RESERVE_FLOOR%. Anything
            left of this is the harvester's playground; right of it is reserved
            for live polling. Helps the operator see where the harvester stops. */}
        <div
          className="absolute top-0 bottom-0 w-px bg-amber-400/80"
          style={{ left: `${reservePct}%` }}
          title={`Live reserve floor (${reserveFloor.toLocaleString()})`}
        />
      </div>
      <div className="flex justify-between text-[10px] text-slate-600 mt-1">
        <span>0</span>
        <span style={{ marginRight: `${100 - reservePct}%` }}>
          reserve {reserveFloor.toLocaleString()}
        </span>
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

function PerMinuteBar({
  value,
  burning,
}: {
  value: number | null
  burning: boolean
}) {
  // The api-football per-minute cap on Pro is 300. We surface the *remaining*
  // counter so a burn window approaching the cap is visible at a glance —
  // green when there's headroom, amber under 100, red under 30.
  const CAP = 300
  const v = value ?? null
  if (v == null) {
    return (
      <div className="text-[11px] text-slate-600 font-mono">
        per-minute headroom: no observation yet
      </div>
    )
  }
  const pct = Math.max(0, Math.min(100, (v / CAP) * 100))
  const color =
    v < 30 ? "bg-red-500" : v < 100 ? "bg-amber-500" : "bg-emerald-500"
  return (
    <div>
      <div className="flex justify-between text-[11px] mb-1">
        <span className="text-slate-500 font-mono">
          per-minute headroom · {v}/{CAP}
        </span>
        <span className={burning ? "text-amber-300" : "text-slate-600"}>
          {burning ? "BURN MODE ACTIVE" : "idle"}
        </span>
      </div>
      <div className="h-1 bg-surface-3 rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}


function InventoryCard({ inv }: { inv: Overview["inventory"] }) {
  return (
    <Card
      title="Data inventory"
      subtitle={`We own ${fmtBytes(inv.archive_bytes)} of api-football responses + normalised rows`}
    >
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-2 mb-4">
        {inv.coverage.map((c) => (
          <CoverageCard key={c.key} c={c} />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
            Completed jobs by endpoint
          </div>
          <div className="space-y-1 max-h-64 overflow-y-auto pr-1">
            {inv.endpoint_breakdown.length === 0 && (
              <div className="text-xs text-slate-600">No completed jobs yet.</div>
            )}
            {inv.endpoint_breakdown.map((row) => (
              <div
                key={row.endpoint}
                className="flex items-center justify-between gap-2 text-xs font-mono border border-edge bg-surface-2 rounded px-2 py-1"
              >
                <span className="text-slate-200 truncate">{row.endpoint}</span>
                <span className="shrink-0 text-slate-400">
                  {row.done.toLocaleString()} · ~{fmtBytes(row.avg_bytes)} ·{" "}
                  <span className="text-slate-500">{fmtTimeAgo(row.last_done)}</span>
                </span>
              </div>
            ))}
          </div>
        </div>

        <div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
            Last 7 days · completed jobs
          </div>
          <ActivitySparkline data={inv.activity_7d} />
        </div>
      </div>
    </Card>
  )
}


function SharpOddsCard({ so }: { so: Overview["sharp_odds"] }) {
  const ageMin = so.age_seconds == null ? null : Math.round(so.age_seconds / 60)
  // Status pill colours: emerald when we have a fresh slate and the feature
  // is on, amber when the cache is stale or the feature was disabled, red
  // when there's no data at all.
  const status =
    !so.feature_enabled ? { label: "DISABLED", cls: "bg-amber-500/15 text-amber-300 border-amber-500/30" }
    : so.event_count === 0 ? { label: "NO DATA", cls: "bg-rose-500/15 text-rose-300 border-rose-500/30" }
    : ageMin != null && ageMin > 720 ? { label: "STALE", cls: "bg-amber-500/15 text-amber-300 border-amber-500/30" }
    : { label: "LIVE", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" }

  return (
    <Card
      title="Sharp odds (Pinnacle)"
      subtitle="The model's de-vig anchor — via SportsGameOdds free tier, refreshes every 6h"
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <div className="flex items-baseline gap-3">
          <span className="font-display text-3xl text-slate-100 tabular-nums">{so.event_count}</span>
          <span className="text-xs text-slate-500">WC fixtures with Pinnacle fair odds</span>
        </div>
        <span className={`text-[10px] font-mono uppercase tracking-wider px-2 py-1 rounded border ${status.cls}`}>
          {status.label}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
        <Stat label="Feature flag" value={so.feature_enabled ? "ON" : "OFF"} good={so.feature_enabled} />
        <Stat label="Last refresh" value={ageMin == null ? "never" : `${ageMin} min ago`} good={ageMin != null && ageMin < 720} />
        <Stat label="Monthly budget" value="~120 / 1000" good={true} />
        <Stat label="Refresh interval" value="6 hours" />
      </div>

      {so.sample && (
        <div className="text-xs border border-edge bg-surface-2 rounded p-2">
          <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Sample fixture</div>
          <div className="font-mono text-slate-200 mb-1">
            {so.sample.home_name} v {so.sample.away_name}
            {so.sample.start_time && (
              <span className="text-slate-500"> · {so.sample.start_time.slice(0, 10)}</span>
            )}
          </div>
          <div className="flex flex-wrap gap-1">
            {Object.entries(so.sample.pinnacle).map(([m, dec]) => (
              <span
                key={m}
                className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-surface-3 border border-edge text-slate-300"
              >
                {m} · {dec.toFixed(2)}
              </span>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}


function CoverageCard({
  c,
}: {
  c: Overview["inventory"]["coverage"][number]
}) {
  // Open-ended cards (target=null) show count only — they're depth metrics,
  // not coverage. Coverage cards show have/target + a progress bar.
  if (c.target == null) {
    return (
      <div className="p-2 rounded border border-edge bg-surface-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500">{c.label}</div>
        <div className="font-display text-lg text-slate-100 mt-1">{c.have.toLocaleString()}</div>
        <div className="text-[10px] text-slate-600">{c.unit}</div>
      </div>
    )
  }
  const pct = c.target > 0 ? Math.max(0, Math.min(100, (c.have / c.target) * 100)) : 0
  const color =
    pct >= 90 ? "bg-emerald-500" : pct >= 40 ? "bg-amber-500" : "bg-slate-500"
  return (
    <div className="p-2 rounded border border-edge bg-surface-2">
      <div className="text-[10px] uppercase tracking-wider text-slate-500">{c.label}</div>
      <div className="flex items-baseline gap-1 mt-1">
        <span className="font-display text-lg text-slate-100">{c.have.toLocaleString()}</span>
        <span className="text-[10px] text-slate-500">/ {c.target.toLocaleString()}</span>
      </div>
      <div className="text-[10px] text-slate-600 mb-1">{c.unit}</div>
      <div className="h-1 bg-surface-3 rounded overflow-hidden">
        <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <div className="text-[10px] text-slate-500 text-right mt-0.5">{pct.toFixed(0)}%</div>
    </div>
  )
}


function ActivitySparkline({
  data,
}: {
  data: Overview["inventory"]["activity_7d"]
}) {
  // Hand-rolled inline SVG. No chart lib (matches the rest of the site). Bars
  // are normalised to the max in the window so a 5-day low + 2-day spike is
  // still readable.
  const max = Math.max(1, ...data.map((d) => d.completed))
  const W = 280
  const H = 60
  const pad = 6
  const barW = (W - pad * 2) / data.length - 4
  return (
    <div className="border border-edge bg-surface-2 rounded p-2">
      <svg viewBox={`0 0 ${W} ${H + 18}`} className="w-full">
        {data.map((d, i) => {
          const x = pad + i * (barW + 4)
          const h = (d.completed / max) * H
          const y = H - h
          return (
            <g key={d.date}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={Math.max(h, 1)}
                rx={1}
                className={d.completed > 0 ? "fill-emerald-500" : "fill-surface-3"}
              />
              <text
                x={x + barW / 2}
                y={H + 12}
                textAnchor="middle"
                className="fill-slate-600 text-[8px] font-mono"
              >
                {d.date.slice(5)}
              </text>
            </g>
          )
        })}
      </svg>
      <div className="text-[10px] text-slate-600 font-mono flex justify-between mt-1">
        <span>peak {max.toLocaleString()}/day</span>
        <span>total {data.reduce((a, b) => a + b.completed, 0).toLocaleString()}</span>
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
