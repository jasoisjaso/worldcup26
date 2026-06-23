/**
 * Shared dashboard primitives — formatters + atomic UI components.
 *
 * Extracted from AdminDashboard.tsx 2026-06-23 so every new tile / page
 * (LiveMatchPanel, PickPerformance, CLV report card, etc) can import the
 * same fmt / Kpi / Section / Spinner / Sparkline / Gate without copy-paste
 * drift across files.
 *
 * Style note: every component renders inside the existing surface-1 / edge
 * design language so new tiles drop into AdminDashboard without restyling.
 */

// ── Formatters ─────────────────────────────────────────────────────────────

export function fmt(n: number | null | undefined): string {
  if (n == null) return "—"
  return n.toLocaleString()
}

export function fmtPct(n: number | null | undefined, decimals = 0): string {
  if (n == null) return "—"
  return (n * 100).toFixed(decimals) + "%"
}

export function fmtBytes(b: number | null | undefined): string {
  if (b == null) return "—"
  if (b < 1024) return `${b}B`
  if (b < 1024 * 1024) return `${(b / 1024).toFixed(1)}KB`
  return `${(b / (1024 * 1024)).toFixed(1)}MB`
}

export function fmtAge(seconds: number | null | undefined): string {
  if (seconds == null) return "—"
  if (seconds < 60) return `${seconds}s`
  if (seconds < 3600) return `${Math.round(seconds / 60)}m`
  if (seconds < 86400) return `${Math.round(seconds / 3600)}h`
  return `${Math.round(seconds / 86400)}d`
}

export function fmtTimeAgo(iso: string | null | undefined): string {
  if (!iso) return "never"
  try {
    const secs = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))
    return fmtAge(secs) + " ago"
  } catch { return iso }
}

export function fmtMinutes(min: number | null | undefined): string {
  if (min == null) return "—"
  if (min < 1) return `${Math.round(min * 60)}s`
  if (min < 60) return `${Math.round(min)}m`
  return `${Math.round(min / 60)}h`
}

// Signed percentage with explicit + on positive (for ROI / CLV / drift deltas).
export function fmtPctSigned(n: number | null | undefined, decimals = 1): string {
  if (n == null) return "—"
  const v = n * 100
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(decimals)}%`
}

// ── Atomic UI ──────────────────────────────────────────────────────────────

export type KpiColor = "green" | "amber" | "red" | "neutral"

export function Kpi({
  label, value, sub, color,
}: { label: string; value: string; sub: string; color: KpiColor }) {
  const border =
    color === "green" ? "border-emerald-500/20"
    : color === "amber" ? "border-amber-500/20"
    : color === "red" ? "border-red-500/20"
    : "border-edge"
  const text =
    color === "green" ? "text-emerald-300"
    : color === "amber" ? "text-amber-300"
    : color === "red" ? "text-red-400"
    : "text-white"
  return (
    <div className={`p-3 rounded-xl border ${border} bg-surface-1`}>
      <div className="text-[9px] uppercase tracking-wider text-slate-500 mb-0.5">{label}</div>
      <div className={`font-display text-2xl tabular-nums ${text}`}>{value}</div>
      <div className="text-[10px] text-slate-500 mt-0.5">{sub}</div>
    </div>
  )
}

export function Section({
  title, subtitle, children,
}: { title: string; subtitle?: string; children: React.ReactNode }) {
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

export function Gate({ label, allowed }: { label: string; allowed: boolean }) {
  return (
    <div className={`flex items-center gap-1.5 px-2 py-1 rounded border text-[10px] font-mono ${allowed ? "border-emerald-500/20 bg-emerald-500/5 text-emerald-400" : "border-slate-700 bg-surface-2 text-slate-500"}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${allowed ? "bg-emerald-400" : "bg-slate-600"}`} />
      {label}
    </div>
  )
}

export function Spinner() {
  return (
    <div className="flex gap-1">
      {[0, 150, 300].map(d => (
        <span key={d} className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" style={{ animationDelay: `${d}ms` }} />
      ))}
    </div>
  )
}

export function Sparkline({ data }: { data: Array<{ date: string; completed: number }> }) {
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
