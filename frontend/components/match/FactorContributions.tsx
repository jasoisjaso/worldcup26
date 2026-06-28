import type { MatchPrediction, WhyFactor } from "@/lib/types"
import { WhyChips } from "./WhyChips"

interface Props {
  context?: MatchPrediction["context"]
  factors: WhyFactor[]
}

const LABELS: Array<{ key: keyof NonNullable<MatchPrediction["context"]>; label: string }> = [
  { key: "xg", label: "Club xG form" },
  { key: "lineup", label: "Confirmed lineup" },
  { key: "set_pieces", label: "Set pieces" },
  { key: "h2h", label: "Head-to-head" },
  { key: "rest", label: "Rest days" },
  { key: "travel", label: "Travel" },
  { key: "weather", label: "Weather" },
]

// Anything below this threshold is treated as numerical noise from the model
// pipeline; we don't render it. Picked at 0.5% (0.005 shift on a multiplier).
const NEUTRAL_BAND = 0.005

interface Row {
  label: string
  homeShift: number
  awayShift: number
  netShift: number   // positive = factor favours away, negative = favours home
  magnitude: number
}

function tupleFor(ctx: NonNullable<MatchPrediction["context"]>, key: string): [number, number] | undefined {
  const raw = (ctx as Record<string, unknown>)[key]
  if (Array.isArray(raw) && raw.length >= 2 && typeof raw[0] === "number" && typeof raw[1] === "number") {
    return [raw[0], raw[1]]
  }
  return undefined
}

/**
 * Per-factor contribution viz. Each row shows ONE bar that swings off a centre
 * line — left (emerald) if the factor net-favours home, right (orange) if it
 * net-favours away. The right-hand column keeps the per-side breakdown so the
 * granularity isn't lost (home -2% / away +2%).
 *
 * The previous design rendered TWO bars (one per side) but only drew them when
 * the side's shift was positive. That made a "rest days hurt home, help away"
 * row read as "rest days help away" with no signal that the home side was also
 * being penalised — and a "travel hurts both sides equally" row read as a
 * blank bar because neither side had a positive shift. The single net-shift
 * bar fixes both — opposite-sign factors compound visually, same-sign cancels.
 */
export function FactorContributions({ context, factors }: Props) {
  if (!context) {
    return factors.length > 0 ? <WhyChips factors={factors} /> : null
  }

  const rows: Row[] = []
  for (const def of LABELS) {
    const tup = tupleFor(context, def.key)
    if (!tup) continue
    const home = tup[0] - 1
    const away = tup[1] - 1
    const magnitude = Math.abs(home) + Math.abs(away)
    if (magnitude < NEUTRAL_BAND * 2) continue
    // Net effect on the matchup: away shift minus home shift. Positive = the
    // factor net-favours away (away gets boosted more or hurt less).
    const netShift = away - home
    rows.push({ label: def.label, homeShift: home, awayShift: away, netShift, magnitude })
  }

  if (rows.length === 0) {
    return factors.length > 0 ? <WhyChips factors={factors} /> : null
  }

  rows.sort((a, b) => Math.abs(b.netShift) - Math.abs(a.netShift))
  const top = rows.slice(0, 5)
  const maxNet = Math.max(...top.map((r) => Math.abs(r.netShift)), 0.02)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_auto] items-baseline gap-2">
        <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest">Factor contributions</p>
        <p className="text-[9px] text-slate-700 tabular-nums">
          <span className="text-emerald-400">home</span>
          <span className="mx-1 text-slate-700">←</span>
          <span className="text-slate-600">·</span>
          <span className="mx-1 text-slate-700">→</span>
          <span className="text-orange-400">away</span>
        </p>
      </div>
      <div className="space-y-1.5">
        {top.map((r) => (
          <FactorRow key={r.label} row={r} max={maxNet} />
        ))}
      </div>
    </div>
  )
}

function FactorRow({ row, max }: { row: Row; max: number }) {
  const pct = clamp((Math.abs(row.netShift) / max) * 100) / 2  // half because we render from centre
  const favoursAway = row.netShift > 0
  const favoursHome = row.netShift < 0
  return (
    <div className="grid grid-cols-[80px_1fr_92px] items-center gap-2 text-[10px]">
      <div className="text-slate-500 truncate">{row.label}</div>
      <div className="relative h-2 bg-surface-3 rounded-full overflow-hidden">
        {/* centre tick */}
        <div className="absolute inset-y-0 left-1/2 w-px bg-edge" aria-hidden="true" />
        {favoursHome && (
          <div
            className="absolute inset-y-0 right-1/2 bg-emerald-500/70"
            style={{ width: `${pct}%` }}
          />
        )}
        {favoursAway && (
          <div
            className="absolute inset-y-0 left-1/2 bg-orange-500/70"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      <div className="text-right tabular-nums text-[9.5px]">
        <span className={tone(row.homeShift, "emerald")}>{formatPct(row.homeShift)}</span>
        <span className="text-slate-700 mx-0.5">/</span>
        <span className={tone(row.awayShift, "orange")}>{formatPct(row.awayShift)}</span>
      </div>
    </div>
  )
}

function tone(shift: number, color: "emerald" | "orange"): string {
  if (Math.abs(shift) < NEUTRAL_BAND) return "text-slate-700"
  if (shift > 0) return color === "emerald" ? "text-emerald-400" : "text-orange-400"
  return "text-slate-500"  // negative shift on this side — dim, the visual bar carries the signal
}

function clamp(n: number): number {
  if (n < 0) return 0
  if (n > 100) return 100
  return n
}

function formatPct(shift: number): string {
  const pct = shift * 100
  const sign = pct > 0 ? "+" : ""
  return `${sign}${pct.toFixed(1)}%`
}
