"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"

// ── Types ──────────────────────────────────────────────────────────────────

type Overview = {
  queue: Record<string, number>
  queue_by_endpoint?: Record<string, number>
  raw_blobs: { total: number; processed: number; unprocessed: number }
  tables: Record<string, number>
  throughput_24h: { completed: number; errors: number }
  last_completed: { id: number; endpoint: string; completed_at: string | null; bytes: number | null } | null
  last_error: { id: number; endpoint: string | null; error_type: string | null; error_msg: string | null; logged_at: string | null } | null
  recent_errors: Array<{ id: number; endpoint: string | null; error_type: string | null; error_msg: string | null; logged_at: string | null }>
  quota_budget: {
    hours_since_midnight_utc: number; hours_until_reset: number; phase: number; phase_label: string
    quota_remaining: number | null; per_minute_remaining: number | null
    live_reserve_floor: number; burn_buffer: number; burn_window_minutes: number; burn_rate_per_minute?: number
    daily_calls_made: number; daily_quota: number
    burn_rate_per_hour: number; projected_daily_total: number
    projection_alert: "OK" | "TIGHT" | "EXHAUST_RISK"
    backfill_calls_today: number; harvester_tick: number
    harvester_enabled: boolean; backfill_allowed: boolean; harvester_allowed: boolean
    burn_should_fire: boolean; injuries_allowed: boolean
  }
  feeds: { feeds: Record<string, { label: string; last_success: string | null; age_minutes: number | null; interval_minutes: number; stale: boolean }>; degraded: string[]; all_fresh: boolean }
  caches: Record<string, { path: string; exists: boolean; size_bytes?: number; age_seconds?: number; modified_at?: string; error?: string }>
  inventory: { coverage: Array<{ key: string; label: string; have: number; target: number | null; unit: string }>; endpoint_breakdown: Array<{ endpoint: string; done: number; avg_bytes: number; last_done: string | null }>; activity_7d: Array<{ date: string; completed: number }>; archive_bytes: number }
  sharp_odds: { feature_enabled: boolean; fetched_at: number | null; age_seconds: number | null; event_count: number; sample: { event_id: string; start_time: string | null; home_name: string; away_name: string; pinnacle: Record<string, number> } | null }
  settings: Record<string, { value: string | null; updated_at: string | null }>
  build: { commit: string }
}

const DAILY_QUOTA = 75000

// ── Utilities ──────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined): string {
  if (n == null) return "—"
  return n.toLocaleString()
}

function fmtPct(n: number | null | undefined, decimals = 0): string {
  if (n == null) return "—"
  return (n * 100).toFixed(decimals) + "%"
}

function fmtBytes(b: number | null | undefined): string {
  if (b == null) return "—"
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / (1024 * 1024)).toFixed(1)}MB`
}

function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

function fmtTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "never"
  try {
    const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
    return fmtAge(secs) + " ago"
  } catch { return iso }
}

function fmtMinutes(min: number | null | undefined): string {
  if (min == null) return "—"
  if (min < 1) return `${Math.round(min * 60)}s`
  if (min < 60) return `${Math.round(min)}m`
  return `${Math.round(min / 60)}h`
}

// ── Main Component ─────────────────────────────────────────────────────────

export default function AdminDashboard() {
  const router = useRouter()
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [tick, setTick] = useState(0)

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/proxy/harvester/overview", { cache: "no-store" })
      if (res.status === 401) { router.replace("/admin/login"); return }
      if (!res.ok) { setError((await res.json().catch(() => ({})))?.detail ?? `HTTP ${res.status}`); setLoading(false); return }
      setData(await res.json() as Overview)
      setError(null)
    } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }, [router])

  useEffect(() => { load(); const id = setInterval(() => setTick(t => t + 1), 15000); return () => clearInterval(id) }, [load])
  useEffect(() => { if (tick > 0) load() }, [tick])

  async function action(label: string, path: string) {
    setBusy(label); setResult(null)
    try {
      const res = await fetch(`/api/admin/proxy/${path}`, { method: "POST", cache: "no-store" })
      const body = await res.json().catch(() => ({}))
      setResult({ ok: res.ok, msg: JSON.stringify(body).slice(0, 300) })
      await load()
    } catch (e) { setResult({ ok: false, msg: (e as Error).message }) } finally { setBusy(null) }
  }

  if (loading) return <div className="flex items-center justify-center min-h-[60vh]"><Spinner /></div>
  if (error && !data) return <div className="p-8 text-center"><p className="text-amber-400">{error}</p><button onClick={() => router.replace("/admin/login")} className="mt-4 text-xs underline text-slate-500">Sign in</button></div>
  if (!data) return null

  const q = data.quota_budget
  const quotaPct = q.quota_remaining == null ? null : (q.quota_remaining / (q.daily_quota || DAILY_QUOTA)) * 100
  const paused = !q.harvester_enabled

  // Plain-English read of what the system is doing right now — so you don't have
  // to decode the gauges to know if everything's healthy.
  const statusLine = (() => {
    if (paused) return { tone: "warn", text: "Harvesting is paused. Live scores still update; background data collection is stopped." }
    if (q.projection_alert === "EXHAUST_RISK") return { tone: "bad", text: "Burning quota too fast — on track to run out before the daily reset. Consider pausing." }
    const queue = data.queue.pending ?? 0
    const errs = data.throughput_24h.errors ?? 0
    if (q.burn_should_fire) return { tone: "ok", text: `Burn window active — draining leftover quota at ${q.burn_rate_per_minute ?? 180}/min before reset. ${queue.toLocaleString()} jobs left to fetch.` }
    if (queue === 0) return { tone: "ok", text: "All caught up — the fetch queue is empty and everything's collected." }
    const hrs = q.hours_until_reset?.toFixed(0) ?? "?"
    return { tone: errs > 20 ? "warn" : "ok", text: `Collecting normally — ${queue.toLocaleString()} jobs queued, ${q.daily_calls_made.toLocaleString()} fetched today. Quota resets in ${hrs}h.${errs > 20 ? ` ${errs} errors in 24h — check the error panel.` : ""}` }
  })()
  const statusColor = statusLine.tone === "bad" ? "border-red-500/30 bg-red-500/5 text-red-200"
    : statusLine.tone === "warn" ? "border-amber-500/30 bg-amber-500/5 text-amber-200"
    : "border-emerald-500/25 bg-emerald-500/5 text-emerald-200"

  return (
    <div className="min-h-screen bg-surface-0 text-slate-200">
      {/* Header */}
      <header className="sticky top-0 z-30 bg-surface-0/90 backdrop-blur border-b border-edge px-4 lg:px-8 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-sm font-bold tracking-tight text-white">Harvester Admin</h1>
          <p className="text-[10px] text-slate-500 font-mono mt-0.5">build {data.build.commit.slice(0, 8)} · {fmtTimeAgo(new Date().toISOString())}</p>
        </div>
        <div className="flex items-center gap-2">
          {paused && <span className="text-[10px] font-bold px-2 py-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 uppercase tracking-wider">Paused</span>}
          {q.burn_should_fire && <span className="text-[10px] font-bold px-2 py-1 rounded bg-orange-500/15 text-orange-300 border border-orange-500/30 uppercase tracking-wider animate-pulse">Burn mode</span>}
          <button onClick={() => load()} className="text-[10px] px-2 py-1 rounded border border-edge hover:bg-surface-2 transition font-mono">↻</button>
          <button onClick={async () => { await fetch("/api/admin/auth", { method: "DELETE" }); router.replace("/admin/login") }} className="text-[10px] px-2 py-1 rounded border border-edge hover:bg-surface-2 transition">Sign out</button>
        </div>
      </header>

      <div className="p-4 lg:p-8 max-w-7xl mx-auto space-y-5">

        {/* ── Plain-English status line ───────────────────────────────────── */}
        <div className={`p-3 rounded-lg border text-sm flex items-center gap-2 ${statusColor}`}>
          <span className={`w-2 h-2 rounded-full shrink-0 ${statusLine.tone === "bad" ? "bg-red-400" : statusLine.tone === "warn" ? "bg-amber-400" : "bg-emerald-400"}`} />
          <span>{statusLine.text}</span>
        </div>

        {/* ── Pause / Burn Banner ─────────────────────────────────────────── */}
        {(paused || q.burn_should_fire) && (
          <div className={`p-3 rounded-lg border text-sm flex items-center gap-3 ${paused ? "border-amber-500/30 bg-amber-500/5 text-amber-200" : "border-orange-500/30 bg-orange-500/5 text-orange-200"}`}>
            <div className="flex-1">
              <span className="font-semibold">{paused ? "Harvester is PAUSED — background fetches stopped" : `Burn window active — ${q.hours_until_reset.toFixed(1)}h until reset @ ${q.burn_rate_per_minute ?? 180} calls/min`}</span>
              <span className="text-[11px] text-slate-400 ml-3">{paused ? "Live polling unaffected" : `${q.quota_remaining?.toLocaleString()} calls remain`}</span>
            </div>
            <button
              onClick={() => action(paused ? "resume" : "pause", paused ? "harvester/resume" : "harvester/pause")}
              disabled={!!busy}
              className={`text-[10px] font-bold px-3 py-1.5 rounded uppercase tracking-wider transition ${paused ? "bg-emerald-500 text-black hover:bg-emerald-400" : "bg-amber-500 text-black hover:bg-amber-400"}`}
            >
              {busy === "pause" || busy === "resume" ? "…" : paused ? "Resume" : "Pause"}
            </button>
          </div>
        )}

        {/* ── KPI Row ─────────────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <Kpi label="Quota remaining" value={q.quota_remaining == null ? "—" : q.quota_remaining.toLocaleString()} sub={`${quotaPct?.toFixed(0) ?? "?"}% of ${(q.daily_quota || DAILY_QUOTA).toLocaleString()}`}
            color={quotaPct == null ? "neutral" : quotaPct < 5 ? "red" : quotaPct < 15 ? "amber" : "green"} />
          <Kpi label="Calls today" value={q.daily_calls_made.toLocaleString()} sub={`${q.burn_rate_per_hour}/hr · ~${Math.round(q.projected_daily_total).toLocaleString()} today`}
            color={q.projection_alert === "OK" ? "green" : q.projection_alert === "TIGHT" ? "amber" : "red"} />
          <Kpi label="Queue depth" value={fmt(data.queue.pending)} sub={`${fmt(data.queue.in_progress)} in flight · ${fmt(data.queue.done)} done`} color="green" />
          <Kpi label="Phase" value={q.phase_label} sub={`${q.hours_until_reset.toFixed(1)}h until UTC reset · phase ${q.phase}`} color={q.phase_label === "burn" ? "amber" : "green"} />
        </div>

        {/* ── Quota Bar ───────────────────────────────────────────────────── */}
        <Section title="API Budget" subtitle={`Burn projection: ${q.projection_alert}`}>
          <div className="space-y-3">
            {/* Main quota bar */}
            <div>
              <div className="flex justify-between text-[10px] font-mono mb-1">
                <span className="text-slate-400">{q.quota_remaining?.toLocaleString() ?? "?"} remaining</span>
                <span className="text-slate-500">{(q.daily_quota || DAILY_QUOTA).toLocaleString()}</span>
              </div>
              <div className="h-3 bg-surface-3 rounded-full overflow-hidden relative">
                <div className={`h-full rounded-full transition-all duration-1000 ${quotaPct == null ? "bg-slate-600" : quotaPct < 5 ? "bg-red-500" : quotaPct < 15 ? "bg-amber-500" : "bg-emerald-500"}`}
                  style={{ width: `${Math.max(1, quotaPct ?? 0)}%` }} />
                {/* Reserve floor marker */}
                <div className="absolute top-0 bottom-0 w-0.5 bg-amber-400/60" style={{ left: `${(q.live_reserve_floor / (q.daily_quota || DAILY_QUOTA)) * 100}%` }} title={`Live reserve: ${q.live_reserve_floor.toLocaleString()}`} />
              </div>
              <div className="flex justify-between text-[9px] text-slate-600 mt-0.5 font-mono">
                <span>0</span>
                <span>reserve {q.live_reserve_floor.toLocaleString()}</span>
              </div>
            </div>
            {/* Per-minute headroom */}
            {q.per_minute_remaining != null && (
              <div>
                <div className="flex justify-between text-[10px] font-mono mb-1">
                  <span className="text-slate-500">Per-minute cap</span>
                  <span className="text-slate-400">{q.per_minute_remaining}/300</span>
                </div>
                <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${q.per_minute_remaining < 30 ? "bg-red-500" : q.per_minute_remaining < 100 ? "bg-amber-500" : "bg-emerald-500"}`}
                    style={{ width: `${Math.max(1, (q.per_minute_remaining / 300) * 100)}%` }} />
                </div>
              </div>
            )}
            {/* Gate indicators */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-[10px]">
              <Gate label="Harvester" allowed={q.harvester_allowed} />
              <Gate label="Backfill" allowed={q.backfill_allowed} />
              <Gate label="Injuries" allowed={q.injuries_allowed} />
              <Gate label="Burn mode" allowed={q.burn_should_fire} />
            </div>
            <p className="text-[10px] text-slate-600">A green dot means that collector is allowed to fetch right now; grey means it's gated (waiting on quota, wrong time window, or paused).</p>
          </div>
        </Section>

        {/* ── Queue + Tables ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
          <Section title="Harvest Queue" subtitle={`${fmt(data.queue.pending)} pending across ${data.queue_by_endpoint ? Object.keys(data.queue_by_endpoint).length : 0} endpoints`}>
            {data.queue_by_endpoint && Object.keys(data.queue_by_endpoint).length > 0 && (
              <div className="space-y-1 max-h-72 overflow-y-auto">
                {Object.entries(data.queue_by_endpoint)
                  .sort(([, a], [, b]) => b - a)
                  .slice(0, 12)
                  .map(([ep, cnt]) => {
                    const total = data.queue.pending || 1
                    const pct = (cnt / total) * 100
                    return (
                      <div key={ep} className="flex items-center gap-2 text-[11px] font-mono">
                        <span className="w-32 truncate text-slate-300">{ep}</span>
                        <div className="flex-1 h-2 bg-surface-3 rounded-full overflow-hidden">
                          <div className="h-full bg-emerald-600/60 rounded-full" style={{ width: `${Math.max(0.5, pct)}%` }} />
                        </div>
                        <span className="w-16 text-right tabular-nums text-slate-100">{cnt.toLocaleString()}</span>
                      </div>
                    )
                  })}
              </div>
            )}
          </Section>

          <Section title="Archive Tables" subtitle={`${fmtBytes(data.inventory.archive_bytes)} stored`}>
            <div className="space-y-1 max-h-72 overflow-y-auto">
              {Object.entries(data.tables)
                .sort(([, a], [, b]) => b - a)
                .map(([name, cnt]) => (
                  <div key={name} className="flex items-center justify-between text-[11px] font-mono py-0.5">
                    <span className="text-slate-400 truncate">{name.replace(/_/g, " ")}</span>
                    <span className="tabular-nums text-slate-200">{cnt.toLocaleString()}</span>
                  </div>
                ))}
            </div>
            <div className="mt-3 grid grid-cols-3 gap-2 text-[10px] font-mono border-t border-edge pt-3">
              <div><span className="text-slate-500">Raw</span><br /><span className="text-slate-300">{data.raw_blobs.total.toLocaleString()}</span></div>
              <div><span className="text-slate-500">Processed</span><br /><span className="text-emerald-300">{data.raw_blobs.processed.toLocaleString()}</span></div>
              <div><span className="text-slate-500">Pending</span><br /><span className={data.raw_blobs.unprocessed > 100 ? "text-amber-300" : "text-slate-300"}>{data.raw_blobs.unprocessed.toLocaleString()}</span></div>
            </div>
          </Section>
        </div>

        {/* ── Feed Health ─────────────────────────────────────────────────── */}
        <Section title={`Scheduler Feeds · ${data.feeds.all_fresh ? "all fresh" : `${data.feeds.degraded.length} stale`}`} subtitle="Last-success age per scheduled job">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
            {Object.entries(data.feeds.feeds)
              .sort(([, a], [, b]) => (a.stale === b.stale ? 0 : a.stale ? -1 : 1))
              .map(([fid, info]) => (
                <div key={fid} className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded text-[11px] font-mono border ${info.stale ? "border-amber-500/20 bg-amber-500/5" : "border-transparent"}`}>
                  <div className="min-w-0">
                    <div className="text-slate-200 truncate text-[10px]">{fid}</div>
                    <div className="text-[9px] text-slate-500 truncate">{info.label}</div>
                  </div>
                  <div className="text-right shrink-0">
                    <div className={`text-[10px] ${info.stale ? "text-amber-400" : "text-emerald-400"}`}>
                      {info.last_success ? fmtMinutes(info.age_minutes) : "—"}
                    </div>
                    <div className="text-[8px] text-slate-600">{fmtMinutes(info.interval_minutes)}</div>
                  </div>
                </div>
              ))}
          </div>
        </Section>

        {/* ── Data Inventory ───────────────────────────────────────────────── */}
        <Section title="Data Inventory" subtitle="What we own across all harvested competitions">
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2 mb-4">
            {data.inventory.coverage.map(c => (
              <div key={c.key} className="p-2.5 rounded-lg border border-edge bg-surface-1">
                <div className="text-[9px] uppercase tracking-wider text-slate-500 truncate">{c.label}</div>
                <div className="text-lg font-display text-white mt-0.5 tabular-nums">{c.have.toLocaleString()}</div>
                <div className="text-[9px] text-slate-600">{c.unit}{c.target != null ? ` / ${c.target.toLocaleString()}` : ""}</div>
                {c.target != null && (
                  <div className="h-1 bg-surface-3 rounded-full mt-1.5 overflow-hidden">
                    <div className={`h-full rounded-full ${c.have / c.target > 0.9 ? "bg-emerald-500" : c.have / c.target > 0.4 ? "bg-amber-500" : "bg-slate-500"}`}
                      style={{ width: `${Math.min(100, (c.have / c.target) * 100)}%` }} />
                  </div>
                )}
              </div>
            ))}
          </div>
          {/* Endpoint breakdown */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Completed by endpoint</div>
              <div className="space-y-1 max-h-48 overflow-y-auto">
                {data.inventory.endpoint_breakdown.map(row => (
                  <div key={row.endpoint} className="flex items-center justify-between text-[10px] font-mono px-1.5 py-0.5">
                    <span className="text-slate-300 truncate">{row.endpoint}</span>
                    <span className="text-slate-500 shrink-0 tabular-nums">{row.done.toLocaleString()} · {fmtBytes(row.avg_bytes)} · {fmtTimeAgo(row.last_done)}</span>
                  </div>
                ))}
              </div>
            </div>
            {/* Activity sparkline */}
            <div>
              <div className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">7-day activity</div>
              <Sparkline data={data.inventory.activity_7d} />
            </div>
          </div>
        </Section>

        {/* ── Sharp Odds ───────────────────────────────────────────────────── */}
        {data.sharp_odds.feature_enabled && (
          <Section title="Sharp Odds · Pinnacle" subtitle="The model's de-vig anchor">
            <div className="flex items-center gap-3 flex-wrap text-sm">
              <span className="font-display text-2xl text-white tabular-nums">{data.sharp_odds.event_count}</span>
              <span className="text-slate-500">WC fixtures anchored</span>
              <span className={`text-[10px] font-mono px-2 py-0.5 rounded border ${data.sharp_odds.event_count > 0 ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-300" : "border-amber-500/30 bg-amber-500/10 text-amber-300"}`}>
                {data.sharp_odds.event_count > 0 ? "LIVE" : "NO DATA"}
              </span>
              {data.sharp_odds.sample && (
                <span className="text-[10px] text-slate-500 font-mono">
                  {data.sharp_odds.sample.home_name} v {data.sharp_odds.sample.away_name} · {Object.entries(data.sharp_odds.sample.pinnacle).map(([m, dec]) => `${m} ${(dec as number).toFixed(2)}`).join(" · ")}
                </span>
              )}
            </div>
          </Section>
        )}

        {/* ── Throughput ───────────────────────────────────────────────────── */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          <Section title="24h Throughput">
            <div className="flex items-baseline gap-2">
              <span className="font-display text-2xl text-emerald-300 tabular-nums">{data.throughput_24h.completed.toLocaleString()}</span>
              <span className="text-[11px] text-slate-500">completed</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1">{data.throughput_24h.errors} errors</div>
            {data.last_completed && (
              <div className="mt-2 text-[10px] font-mono text-slate-400 truncate">
                Last: {data.last_completed.endpoint} · {fmtBytes(data.last_completed.bytes)} · {fmtTimeAgo(data.last_completed.completed_at)}
              </div>
            )}
          </Section>

          <Section title="Recent Errors" subtitle={data.recent_errors.length > 0 ? `${data.recent_errors.length} errors` : "None"}>
            {data.recent_errors.length === 0 ? (
              <p className="text-[11px] text-slate-500">No recent errors.</p>
            ) : (
              <div className="space-y-1.5 max-h-32 overflow-y-auto">
                {data.recent_errors.slice(0, 5).map(e => (
                  <div key={e.id} className="text-[10px] font-mono p-1.5 rounded border border-amber-500/15 bg-amber-500/5">
                    <span className="text-amber-400">{e.endpoint}</span>
                    <span className="text-slate-500 ml-2">{e.error_type}</span>
                    <span className="text-slate-600 ml-2">{fmtTimeAgo(e.logged_at)}</span>
                  </div>
                ))}
              </div>
            )}
          </Section>

          <Section title="Caches">
            <div className="space-y-1.5">
              {Object.entries(data.caches).map(([name, info]) => (
                <div key={name} className="flex items-center justify-between text-[10px] font-mono">
                  <span className="text-slate-400">{name}</span>
                  <span className={info.exists ? "text-emerald-400" : "text-amber-400"}>
                    {info.exists ? `${fmtBytes(info.size_bytes)} · ${fmtAge(info.age_seconds)}` : "missing"}
                  </span>
                </div>
              ))}
            </div>
          </Section>
        </div>

        {/* ── Manual Actions ───────────────────────────────────────────────── */}
        <Section title="Manual Actions" subtitle="Use sparingly — each seed queues real API calls">
          <div className="flex flex-wrap gap-2">
            <button onClick={() => action("seed-heavy", "harvester/seed/heavy")} disabled={busy === "seed-heavy"}
              className="text-[11px] font-bold px-4 py-2 rounded-lg bg-emerald-600 text-white hover:bg-emerald-500 transition disabled:opacity-50 uppercase tracking-wider">
              {busy === "seed-heavy" ? "…" : "Seed Everything"}
            </button>
            <button onClick={() => action("seed-squads", "harvester/seed/wc-squads")} disabled={busy === "seed-squads"}
              className="text-[11px] px-3 py-2 rounded-lg border border-edge text-slate-300 hover:bg-surface-2 transition disabled:opacity-50">
              WC Squads
            </button>
            <button onClick={() => action("seed-wc-players", "harvester/seed/wc-fixture-players")} disabled={busy === "seed-wc-players"}
              className="text-[11px] px-3 py-2 rounded-lg border border-edge text-slate-300 hover:bg-surface-2 transition disabled:opacity-50">
              WC Fixture Players
            </button>
            <button onClick={() => action("run-one", "harvester/run-one")} disabled={busy === "run-one"}
              className="text-[11px] px-3 py-2 rounded-lg border border-edge text-slate-300 hover:bg-surface-2 transition disabled:opacity-50">
              Run One Tick
            </button>
          </div>
          {result && (
            <div className={`mt-3 text-[10px] font-mono p-2 rounded border ${result.ok ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-300" : "border-amber-500/20 bg-amber-500/5 text-amber-300"}`}>
              {result.msg}
            </div>
          )}
        </Section>

      </div>
    </div>
  )
}

// ── Sub-components ─────────────────────────────────────────────────────────

function Kpi({ label, value, sub, color }: { label: string; value: string; sub: string; color: "green" | "amber" | "red" | "neutral" }) {
  const border = color === "green" ? "border-emerald-500/20" : color === "amber" ? "border-amber-500/20" : color === "red" ? "border-red-500/20" : "border-edge"
  const text = color === "green" ? "text-emerald-300" : color === "amber" ? "text-amber-300" : color === "red" ? "text-red-400" : "text-white"
  return (
    <div className={`p-3 rounded-xl border ${border} bg-surface-1`}>
      <div className="text-[9px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
      <div className={`font-display text-2xl tabular-nums ${text}`}>{value}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>
    </div>
  )
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl border border-edge bg-surface-1 p-4">
      <div className="mb-3">
        <h2 className="text-xs font-bold text-white uppercase tracking-wider">{title}</h2>
        {subtitle && <p className="text-[10px] text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </section>
  )
}

function Gate({ label, allowed }: { label: string; allowed: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-mono ${allowed ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : "border-slate-700 bg-surface-2 text-slate-500"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${allowed ? "bg-emerald-400" : "bg-slate-600"}`} />
      {label}
    </div>
  )
}

function Spinner() {
  return (
    <div className="flex gap-1">
      {[0, 150, 300].map(d => (
        <span key={d} className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" style={{ animationDelay: `${d}ms` }} />
      ))}
    </div>
  )
}

function Sparkline({ data }: { data: Array<{ date: string; completed: number }> }) {
  const max = Math.max(1, ...data.map(d => d.completed))
  const W = 260; const H = 50; const pad = 4; const barW = Math.max(1, (W - pad * 2) / data.length - 3)
  return (
    <div className="border border-edge bg-surface-2 rounded-lg p-2">
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="w-full">
        {data.map((d, i) => {
          const x = pad + i * (barW + 3)
          const h = Math.max(1, (d.completed / max) * H)
          return (
            <g key={d.date}>
              <rect x={x} y={H - h} width={barW} height={h} rx={1} className={d.completed > 0 ? "fill-emerald-500/70" : "fill-surface-4"} />
              <text x={x + barW / 2} y={H + 11} textAnchor="middle" className="fill-slate-600 text-[7px] font-mono">{d.date.slice(5)}</text>
            </g>
          )
        })}
      </svg>
      <div className="flex justify-between text-[9px] text-slate-600 font-mono mt-1">
        <span>peak {max.toLocaleString()}</span>
        <span>{data.reduce((a, b) => a + b.completed, 0).toLocaleString()} total</span>
      </div>
    </div>
  )
}
