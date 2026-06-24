"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { useRouter } from "next/navigation"
import {
  fmt, fmtPct, fmtBytes, fmtAge, fmtTimeAgo, fmtMinutes,
  Kpi, Section, Gate, Spinner, Sparkline,
} from "@/components/admin/parts"
import { LiveMatchPanel } from "@/components/admin/LiveMatchPanel"
import { PickPerformance } from "@/components/admin/PickPerformance"
import { CommandPalette, type PaletteCommand } from "@/components/admin/CommandPalette"
import { AdminActions } from "@/components/admin/AdminActions"

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
    harvest_batch_size?: number; harvest_rate_per_hour?: number
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
  match_anomalies?: {
    count: number
    by_issue: Record<string, number>
    items: Array<{
      match_id: string
      label: string
      kickoff: string | null
      status: string
      interruption_status: string | null
      interruption_reason?: string | null
      interruption_started_at?: string | null
      partial_score?: string | null
      issue: "interrupted" | "ghost_no_result"
    }>
  }
  // Live Match Panel — operator's "what's happening right now" view.
  // See backend.api.routes.harvester_admin._live_panel for shape.
  live_panel?: {
    count: number
    items: Array<{
      match_id: string; label: string; matchday: number | null; group: string | null
      is_knockout: boolean; status: string; elapsed_min: number | null
      home_score: number | null; away_score: number | null
      shootout_home_score: number | null; shootout_away_score: number | null
      tick_age_secs: number | null; stale: boolean; push_count_1h: number
      recent_events: Array<{ minute: number; type: string; detail: string | null; player: string | null; team: string | null }>
    }>
  }
  // Pick Performance — rolling 30d unit-stake P&L. See _pick_performance.
  pick_performance?: {
    window_days: number
    total: { n: number; wins: number; hit_rate: number | null; stake_u: number; profit_u: number; roi: number | null }
    clv: { n: number; avg: number | null }
    by_market: Record<string, { n: number; wins: number; hit_rate: number | null; profit_u: number; roi: number | null }>
    by_confidence: Record<string, { n: number; wins: number; hit_rate: number | null; profit_u: number; roi: number | null }>
  }
  // Admin Actions audit log — tail of admin_actions table.
  admin_actions?: {
    count: number
    items: Array<{
      id: number
      action: string
      endpoint: string
      requested_at: string | null
      completed_at: string | null
      status: "pending" | "ok" | "error"
      error: string | null
    }>
  }
  // Last 20 commits from GitHub — cached 5min server-side.
  changelog?: {
    items: Array<{ sha: string; subject: string; iso: string | null; author: string | null }>
    note: string | null
  }
  settings: Record<string, { value: string | null; updated_at: string | null }>
  build: { commit: string }
}

const DAILY_QUOTA = 75000

// ── Utilities ──────────────────────────────────────────────────────────────

// Formatters + atomic UI live in @/components/admin/parts so new tiles
// can share them without copy-paste drift.

// ── Main Component ─────────────────────────────────────────────────────────

export default function AdminDashboard() {
  const router = useRouter()
  const [data, setData] = useState<Overview | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState<string | null>(null)
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null)
  const [tick, setTick] = useState(0)
  // Auto-refresh toggle. When paused, the 15s poll loop stops firing but
  // the manual refresh button still works. Useful when inspecting a
  // snapshot of data without it shifting under you (e.g. comparing two
  // tiles or copying values). Persists across re-renders only — resets
  // on full page reload, which is fine.
  const [pollPaused, setPollPaused] = useState(false)
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null)

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/admin/proxy/harvester/overview", { cache: "no-store" })
      if (res.status === 401) { router.replace("/admin/login"); return }
      if (!res.ok) { setError((await res.json().catch(() => ({})))?.detail ?? `HTTP ${res.status}`); setLoading(false); return }
      setData(await res.json() as Overview)
      setError(null)
      setLastRefreshed(new Date())
    } catch (e) { setError((e as Error).message) } finally { setLoading(false) }
  }, [router])

  useEffect(() => {
    load()
    const id = setInterval(() => setTick(t => t + 1), 15000)
    return () => clearInterval(id)
  }, [load])
  // Re-poll on tick unless paused — pause check happens INSIDE the effect
  // so toggling pollPaused doesn't have to re-create the interval.
  useEffect(() => { if (tick > 0 && !pollPaused) load() }, [tick, pollPaused, load])

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

  // Burnout ETA: at current burn rate, when will usable quota (above the
  // live reserve floor) run out? Surfaced in the header so the operator
  // knows whether "pause" is a 'sometime today' choice or 'right now'.
  const burnoutEtaMinutes = (() => {
    if (!q.quota_remaining || q.quota_remaining <= q.live_reserve_floor) return null
    const usable = q.quota_remaining - q.live_reserve_floor
    const perMinute = q.burn_rate_per_hour > 0 ? q.burn_rate_per_hour / 60 : 0
    if (perMinute <= 0) return null
    return Math.round(usable / perMinute)
  })()
  const fmtEta = (m: number | null) => {
    if (m == null) return null
    if (m < 60) return `${m}m`
    const h = Math.floor(m / 60); const mm = m % 60
    return `${h}h ${mm}m`
  }
  const inDanger = q.projection_alert === "EXHAUST_RISK" && !paused

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
    // Real Phase-2 collection rate at the current quota tier. Flag if it's
    // dragging well below the 3,000/h target while there's still a queue to
    // drain and quota to spend — that's the "burning too slow" symptom.
    const rate = q.harvest_rate_per_hour ?? 0
    const tooSlow = rate > 0 && rate < 3000 && queue > 0 && q.phase === 2
    const rateText = rate > 0 ? ` Collecting at ${rate.toLocaleString()}/hr.` : ""
    if (tooSlow) return { tone: "warn", text: `Collecting at ${rate.toLocaleString()}/hr — below the 3,000/hr target (quota tier throttled). ${queue.toLocaleString()} jobs queued, ${q.daily_calls_made.toLocaleString()} fetched today. Resets in ${hrs}h.` }
    return { tone: errs > 20 ? "warn" : "ok", text: `Collecting normally —${rateText} ${queue.toLocaleString()} jobs queued, ${q.daily_calls_made.toLocaleString()} fetched today. Quota resets in ${hrs}h.${errs > 20 ? ` ${errs} errors in 24h — check the error panel.` : ""}` }
  })()
  const statusColor = statusLine.tone === "bad" ? "border-red-500/30 bg-red-500/5 text-red-200"
    : statusLine.tone === "warn" ? "border-amber-500/30 bg-amber-500/5 text-amber-200"
    : "border-emerald-500/25 bg-emerald-500/5 text-emerald-200"

  // Command palette commands — built fresh per render so destructive-action
  // labels can reflect the current state ("Pause" vs "Resume"). Anchors use
  // the auto-id pattern from <Section> so adding a new section automatically
  // makes it jumpable.
  const scrollTo = (id: string) => () => {
    const el = document.getElementById(id)
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
  }
  const commands: PaletteCommand[] = [
    // Navigation — one entry per top-level section. IDs match the auto-slug
    // produced by parts.tsx <Section>.
    { id: "nav-quota",       label: "Quota Budget",       hint: "burn projection + gates",      kind: "nav", run: scrollTo("section-api-budget") },
    { id: "nav-live",        label: "Live Matches",       hint: "per-fixture state + tickets",  kind: "nav", run: scrollTo("section-live-matches") },
    { id: "nav-picks",       label: "Pick Performance",   hint: "30d ROI / hit rate / CLV",     kind: "nav", run: scrollTo("section-pick-performance") },
    { id: "nav-admin-acts",  label: "Admin Actions",      hint: "audit log of state changes",   kind: "nav", run: scrollTo("section-admin-actions") },
    { id: "nav-anomalies",   label: "Match Anomalies",    hint: "delayed / ghost matches",      kind: "nav", run: scrollTo("section-match-anomalies") },
    { id: "nav-queue",       label: "Harvest Queue",      hint: "pending API jobs by endpoint", kind: "nav", run: scrollTo("section-harvest-queue") },
    { id: "nav-tables",      label: "Archive Tables",     hint: "DB row counts + size",         kind: "nav", run: scrollTo("section-archive-tables") },
    { id: "nav-feeds",       label: "Scheduler Feeds",    hint: "all 23 scheduled job ages",    kind: "nav", run: scrollTo("section-scheduler-feeds") },
    { id: "nav-inventory",   label: "Data Inventory",     hint: "coverage by competition",      kind: "nav", run: scrollTo("section-data-inventory") },
    { id: "nav-sharp",       label: "Sharp Odds",         hint: "Pinnacle model anchor",        kind: "nav", run: scrollTo("section-sharp-odds-pinnacle") },
    { id: "nav-throughput",  label: "24h Throughput",     hint: "completed + errors sparkline", kind: "nav", run: scrollTo("section-24h-throughput") },
    { id: "nav-errors",      label: "Recent Errors",      hint: "last 50 harvest failures",     kind: "nav", run: scrollTo("section-recent-errors") },
    { id: "nav-caches",      label: "Caches",             hint: "disk file freshness",          kind: "nav", run: scrollTo("section-caches") },
    { id: "nav-changelog",   label: "Changelog",          hint: "last 20 commits to main",      kind: "nav", run: scrollTo("section-changelog") },
    { id: "nav-actions",     label: "Manual Actions",     hint: "seed buttons",                 kind: "nav", run: scrollTo("section-manual-actions") },
    // Actions — destructive ones gate via typed confirmation per anti-pattern #6.
    {
      id: "act-pause-resume",
      label: paused ? "Resume harvester" : "Pause harvester",
      hint: paused ? "re-enable all background API calls" : "stop all background API calls — live polling unaffected",
      kind: "action",
      destructive: !paused,
      confirmWord: "PAUSE",
      run: () => action(paused ? "resume" : "pause", paused ? "harvester/resume" : "harvester/pause"),
    },
    { id: "act-run-one",     label: "Run one harvest pass",        hint: "fire a single job from the queue",          kind: "action", run: () => action("run-one", "harvester/run-one") },
    { id: "act-refresh",     label: "Refresh dashboard",           hint: "re-poll /overview now",                     kind: "action", run: () => load() },
    {
      id: "act-seed-squads",
      label: "Seed WC squads",
      hint: "queue squad + player fetches for all 48 nations (~96 calls)",
      kind: "action",
      destructive: true,
      confirmWord: "SEED",
      run: () => action("seed-squads", "harvester/seed/wc-squads"),
    },
    {
      id: "act-seed-heavy",
      label: "Seed heavy (full backfill)",
      hint: "all leagues + full player histories — burns a LOT of quota",
      kind: "action",
      destructive: true,
      confirmWord: "HEAVY",
      run: () => action("seed-heavy", "harvester/seed/heavy"),
    },
  ]

  return (
    <div className="min-h-screen bg-surface-0 text-slate-200">
      <CommandPalette commands={commands} />
      {/* Header */}
      <header className="sticky top-0 z-30 bg-surface-0/90 backdrop-blur border-b border-edge px-4 lg:px-8 py-3 flex items-center justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-sm font-bold tracking-tight text-white">Harvester Admin</h1>
          <p className="text-[10px] text-slate-500 font-mono mt-0.5">build {data.build.commit.slice(0, 8)} · {fmtTimeAgo(new Date().toISOString())}</p>
        </div>
        <div className="flex items-center gap-2">
          {paused && <span className="text-[10px] font-bold px-2 py-1 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30 uppercase tracking-wider">Paused</span>}
          {q.burn_should_fire && <span className="text-[10px] font-bold px-2 py-1 rounded bg-orange-500/15 text-orange-300 border border-orange-500/30 uppercase tracking-wider animate-pulse">Burn mode</span>}
          {/* Always-visible pause/resume. Visual treatment escalates when
              EXHAUST_RISK is firing — operator needs the action in their
              line of sight, not buried inside a conditional banner. */}
          <button
            onClick={() => action(paused ? "resume" : "pause", paused ? "harvester/resume" : "harvester/pause")}
            disabled={!!busy}
            title={paused ? "Resume background fetches" : "Pause background fetches (live polling unaffected)"}
            className={`text-[10px] font-bold px-3 py-1.5 rounded uppercase tracking-wider transition disabled:opacity-50 ${
              paused
                ? "bg-emerald-500 text-black hover:bg-emerald-400"
                : inDanger
                  ? "bg-amber-500 text-black hover:bg-amber-400 animate-pulse"
                  : "border border-slate-600 text-slate-300 hover:bg-surface-2"
            }`}
          >
            {busy === "pause" || busy === "resume" ? "…" : paused ? "Resume" : inDanger ? "Pause now" : "Pause"}
          </button>
          {burnoutEtaMinutes != null && !paused && (
            <span className={`text-[10px] font-mono px-2 py-1 rounded border ${inDanger ? "border-amber-500/40 bg-amber-500/10 text-amber-200" : "border-edge text-slate-500"}`}
              title={`At ${q.burn_rate_per_hour.toLocaleString()}/hr you'll hit the live-reserve floor in this much time. Quota fully resets in ${q.hours_until_reset.toFixed(1)}h.`}>
              ⏱ {fmtEta(burnoutEtaMinutes)} until reserve
            </span>
          )}
          {/* Refresh cluster: pause-toggle + last-poll age + manual refresh.
              Pause is amber when active so it's obvious the dashboard isn't
              live. Manual refresh always works regardless of pause state. */}
          <div className="flex items-center gap-1.5 border border-edge rounded px-1.5 py-0.5 font-mono">
            <button
              onClick={() => setPollPaused((v) => !v)}
              className={`text-[10px] w-5 text-center transition-colors ${pollPaused ? "text-amber-400" : "text-slate-500 hover:text-slate-200"}`}
              title={pollPaused ? "Auto-refresh paused — click to resume" : "Pause auto-refresh"}
              aria-label={pollPaused ? "Resume auto-refresh" : "Pause auto-refresh"}
            >
              {pollPaused ? "▶" : "❚❚"}
            </button>
            <span className="text-[9px] text-slate-600 tabular-nums w-12 text-right">
              {lastRefreshed ? fmtTimeAgo(lastRefreshed.toISOString()) : "—"}
            </span>
            <button
              onClick={() => load()}
              className="text-[10px] text-slate-500 hover:text-slate-200 w-5 text-center transition-colors"
              title="Refresh now"
              aria-label="Refresh dashboard"
            >
              ↻
            </button>
          </div>
          <button onClick={async () => { await fetch("/api/admin/auth", { method: "DELETE" }); router.replace("/admin/login") }} className="text-[10px] px-2 py-1 rounded border border-edge hover:bg-surface-2 transition">Sign out</button>
        </div>
      </header>

      <div className="p-4 lg:p-8 max-w-7xl mx-auto space-y-5">

        {/* ── Plain-English status line ───────────────────────────────────── */}
        <div className={`p-3 rounded-lg border text-sm flex items-center gap-2 ${statusColor}`}>
          <span className={`w-2 h-2 rounded-full shrink-0 ${statusLine.tone === "bad" ? "bg-red-400" : statusLine.tone === "warn" ? "bg-amber-400" : "bg-emerald-400"}`} />
          <span>{statusLine.text}</span>
        </div>

        {/* ── Emergency / Pause / Burn Banner ─────────────────────────────── */}
        {inDanger && (
          <div className="p-3 rounded-lg border border-red-500/40 bg-red-500/10 text-red-100 flex items-center gap-3">
            <span className="text-lg leading-none">⚠</span>
            <div className="flex-1">
              <span className="font-semibold">Quota exhaustion projected — projected {Math.round(q.projected_daily_total).toLocaleString()} vs {(q.daily_quota || DAILY_QUOTA).toLocaleString()} daily.</span>
              <span className="text-[11px] text-red-200/80 ml-3">
                Burning {q.burn_rate_per_hour.toLocaleString()}/hr · usable reserve hit in {fmtEta(burnoutEtaMinutes) ?? "—"} · reset in {q.hours_until_reset.toFixed(1)}h.
              </span>
            </div>
            <button
              onClick={() => action("pause", "harvester/pause")}
              disabled={!!busy}
              className="text-[10px] font-bold px-3 py-1.5 rounded uppercase tracking-wider transition bg-red-500 text-white hover:bg-red-400 disabled:opacity-50 animate-pulse"
            >
              {busy === "pause" ? "…" : "Pause now"}
            </button>
          </div>
        )}
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
          <Kpi label="Calls today" value={q.daily_calls_made.toLocaleString()} sub={`${q.harvest_rate_per_hour ? `now ${q.harvest_rate_per_hour.toLocaleString()}/hr · ` : ""}avg ${q.burn_rate_per_hour}/hr · ~${Math.round(q.projected_daily_total).toLocaleString()} today`}
            color={q.projection_alert === "OK" ? "green" : q.projection_alert === "TIGHT" ? "amber" : "red"} />
          <Kpi label="Queue depth" value={fmt(data.queue.pending)} sub={`${fmt(data.queue.in_progress)} in flight · ${fmt(data.queue.done)} done`} color="green" />
          <Kpi label="Phase" value={q.phase_label} sub={`${q.hours_until_reset.toFixed(1)}h until UTC reset · phase ${q.phase}`} color={q.phase_label === "burn" ? "amber" : "green"} />
        </div>

        {/* ── Quota Bar ───────────────────────────────────────────────────── */}
        <Section
          title="API Budget"
          subtitle={`Burn projection: ${q.projection_alert}`}
          helpText={
            <div className="space-y-1.5">
              <p><span className="text-amber-300 font-bold">Burn rate</span> — api-football calls/hour right now, projected forward to end of day.</p>
              <p><span className="text-amber-300 font-bold">Live reserve floor</span> — calls we ALWAYS keep aside for live polling (2,500). Backfill + harvester refuse to run below this.</p>
              <p><span className="text-amber-300 font-bold">Phase 1/2/3</span> — backfill / steady / burn. Phase 3 = quota tight, only essential calls fire.</p>
              <p><span className="text-amber-300 font-bold">Burn buffer</span> — small pad above the floor before the burn-rate emergency kicks in.</p>
            </div>
          }
        >
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
        <Section
          title={`Scheduler Feeds · ${data.feeds.all_fresh ? "all fresh" : `${data.feeds.degraded.length} stale`}`}
          subtitle="Last-success age per scheduled job"
          helpText={
            <div className="space-y-1.5">
              <p>Each row = one background job. Number is how long since its last successful run.</p>
              <p><span className="text-emerald-300 font-bold">Green</span> = fresh (within interval). <span className="text-amber-300 font-bold">Amber</span> = stale (overdue). <span className="text-slate-400 font-bold">Grey "pending"</span> = hasn't run yet (post-deploy or daily-only job).</p>
            </div>
          }
        >
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-1.5">
            {Object.entries(data.feeds.feeds)
              .sort(([, a], [, b]) => (a.stale === b.stale ? 0 : a.stale ? -1 : 1))
              .map(([fid, info]) => {
                // Three states instead of two: stale (amber) / fresh (green) /
                // pending (grey) — was bucketed as fresh-with-"—" before
                // which made it look like a healthy feed with missing data
                // instead of a job that's never run since the container started.
                const hasRun = !!info.last_success
                const ageColor = info.stale ? "text-amber-400"
                  : hasRun ? "text-emerald-400"
                  : "text-slate-500"
                const ageText = hasRun ? fmtMinutes(info.age_minutes) : "pending"
                return (
                  <div key={fid} className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded text-[11px] font-mono border ${info.stale ? "border-amber-500/20 bg-amber-500/5" : "border-transparent"}`}>
                    <div className="min-w-0">
                      <div className="text-slate-200 truncate text-[10px]">{fid}</div>
                      <div className="text-[9px] text-slate-500 truncate">{info.label}</div>
                    </div>
                    <div className="text-right shrink-0">
                      <div className={`text-[10px] ${ageColor}`}>{ageText}</div>
                      <div className="text-[8px] text-slate-600">every {fmtMinutes(info.interval_minutes)}</div>
                    </div>
                  </div>
                )
              })}
          </div>
        </Section>

        {/* ── Match Anomalies ─────────────────────────────────────────────
            Born from the FRA-IRQ 2026-06-22 weather-suspension incident.
            Surfaces matches that the lifecycle layer flagged as off-track
            (delayed/postponed/abandoned/awarded) plus "ghost" rows whose
            kickoff is hours in the past but never resolved. Either count
            > 0 here is a signal to look at the live poller. */}
        {data.match_anomalies && data.match_anomalies.count > 0 && (
          <Section
            title={`Match Anomalies · ${data.match_anomalies.count}`}
            subtitle="Lifecycle states outside the normal upcoming → live → complete flow"
          >
            <div className="flex flex-wrap gap-2 mb-3">
              {Object.entries(data.match_anomalies.by_issue).map(([issue, n]) => (
                <span
                  key={issue}
                  className={`text-[10px] font-mono px-2 py-0.5 rounded border ${
                    issue === "ghost_no_result"
                      ? "border-red-500/40 bg-red-500/10 text-red-300"
                      : "border-amber-500/40 bg-amber-500/10 text-amber-300"
                  }`}
                >
                  {issue.replace(/_/g, " ")}: {n}
                </span>
              ))}
            </div>
            <div className="space-y-1.5">
              {data.match_anomalies.items.map((it) => (
                <div
                  key={it.match_id}
                  className={`flex items-center justify-between gap-3 px-2.5 py-2 rounded text-[11px] font-mono border ${
                    it.issue === "ghost_no_result"
                      ? "border-red-500/30 bg-red-500/5"
                      : "border-amber-500/30 bg-amber-500/5"
                  }`}
                >
                  <div className="min-w-0 flex-1">
                    <div className="text-slate-200">
                      <span className="text-slate-500">{it.match_id}</span>{" "}
                      {it.label}
                      {it.partial_score && (
                        <span className="text-amber-400 ml-2">({it.partial_score})</span>
                      )}
                    </div>
                    {it.interruption_reason && (
                      <div className="text-[9px] text-slate-500 truncate mt-0.5">
                        {it.interruption_reason}
                      </div>
                    )}
                  </div>
                  <div className="text-right shrink-0">
                    <div className="text-[10px] uppercase tracking-wider">
                      <span
                        className={
                          it.issue === "ghost_no_result"
                            ? "text-red-400"
                            : "text-amber-400"
                        }
                      >
                        {it.interruption_status || it.issue}
                      </span>
                    </div>
                    <div className="text-[9px] text-slate-600">
                      ko {fmtTimeAgo(it.kickoff)}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )}

        {/* ── Live Match Panel — what's happening RIGHT NOW (per-match) ───── */}
        <LiveMatchPanel initial={data.live_panel ?? null} />

        {/* ── Pick Performance — rolling 30d unit P&L / ROI / CLV ────────── */}
        <PickPerformance data={data.pick_performance ?? null} />

        {/* ── Admin Actions audit log — every state-changing POST tailed ── */}
        <AdminActions data={data.admin_actions ?? null} />

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
          <Section
            title="Sharp Odds · Pinnacle"
            subtitle="The model's de-vig anchor"
            helpText={
              <p>Pinnacle is the sharpest soccer bookmaker. We pull their 1X2 odds, de-vig them, and use them as a reference probability the model is graded against. Drives the Calibration tile + CLV calculation.</p>
            }
          >
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
        {/* ── Changelog — last 20 commits via GitHub API (5-min cached) ──── */}
        {data.changelog && (
          <Section
            title="Changelog"
            subtitle={
              data.changelog.note
                ? `Couldn't fetch — ${data.changelog.note}`
                : `Last ${data.changelog.items.length} commits from origin/main`
            }
            helpText={
              <p>What shipped since you last looked. Pulled from the public GitHub repo every 5 minutes — so newly-pushed commits show up after the next cache miss.</p>
            }
          >
            {data.changelog.items.length === 0 ? (
              <p className="text-[11px] text-slate-600">No commits available.</p>
            ) : (
              <div className="border border-edge bg-surface-2 rounded-lg divide-y divide-edge/40 max-h-72 overflow-y-auto">
                {data.changelog.items.map((c) => (
                  <a
                    key={c.sha}
                    href={`https://github.com/jasoisjaso/worldcup26/commit/${c.sha}`}
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-start gap-3 px-3 py-2 text-[11px] hover:bg-surface-1 transition-colors"
                  >
                    <span className="font-mono text-[10px] text-amber-400 tabular-nums shrink-0 w-12">{c.sha}</span>
                    <span className="flex-1 truncate text-slate-200" title={c.subject}>{c.subject}</span>
                    <span className="text-[10px] text-slate-600 font-mono shrink-0 tabular-nums">
                      {fmtTimeAgo(c.iso)}
                    </span>
                  </a>
                ))}
              </div>
            )}
          </Section>
        )}

        <Section
          title="Manual Actions"
          subtitle="Use sparingly — each seed queues real API calls"
          helpText={
            <div className="space-y-1.5">
              <p>These buttons queue real api-football jobs and burn quota. Cmd+K → action is the same flow with typed-confirmation on destructive ones.</p>
              <p><span className="text-amber-300 font-bold">Seed WC squads</span> — ~96 calls (48 nations × 2 endpoints)</p>
              <p><span className="text-amber-300 font-bold">Seed heavy</span> — 200,000+ jobs, hours of harvest work. Only run with plentiful quota.</p>
              <p><span className="text-amber-300 font-bold">Run one</span> — fires a single queued job for testing.</p>
            </div>
          }
        >
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

