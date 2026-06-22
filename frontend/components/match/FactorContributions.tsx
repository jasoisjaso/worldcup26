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

const NEUTRAL_BAND = 0.005

interface Row {
  label: string
  homeShift: number
  awayShift: number
  magnitude: number
}

function tupleFor(ctx: NonNullable<MatchPrediction["context"]>, key: string): [number, number] | undefined {
  const raw = (ctx as Record<string, unknown>)[key]
  if (Array.isArray(raw) && raw.length >= 2 && typeof raw[0] === "number" && typeof raw[1] === "number") {
    return [raw[0], raw[1]]
  }
  return undefined
}

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
    rows.push({ label: def.label, homeShift: home, awayShift: away, magnitude })
  }

  if (rows.length === 0) {
    return factors.length > 0 ? <WhyChips factors={factors} /> : null
  }

  rows.sort((a, b) => b.magnitude - a.magnitude)
  const top = rows.slice(0, 5)
  const maxShift = Math.max(...top.map((r) => Math.max(Math.abs(r.homeShift), Math.abs(r.awayShift))), 0.02)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-[1fr_auto] items-baseline gap-2">
        <p className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest">Factor contributions</p>
        <p className="text-[9px] text-slate-700 tabular-nums">
          <span className="text-emerald-400">home</span>
          <span className="mx-1 text-slate-700">vs</span>
          <span className="text-orange-400">away</span>
        </p>
      </div>
      <div className="space-y-1.5">
        {top.map((r) => (
          <FactorRow key={r.label} row={r} max={maxShift} />
        ))}
      </div>
    </div>
  )
}

function FactorRow({ row, max }: { row: Row; max: number }) {
  const homePct = clamp((Math.abs(row.homeShift) / max) * 100)
  const awayPct = clamp((Math.abs(row.awayShift) / max) * 100)
  const homeLeans = row.homeShift > NEUTRAL_BAND
  const awayLeans = row.awayShift > NEUTRAL_BAND
  return (
    <div className="grid grid-cols-[80px_1fr_80px] items-center gap-2 text-[10px]">
      <div className="text-slate-500 truncate">{row.label}</div>
      <div className="relative h-2 bg-surface-3 rounded-full overflow-hidden">
        <div className="absolute inset-y-0 left-1/2 w-px bg-edge" aria-hidden="true" />
        {homeLeans && (
          <div
            className="absolute inset-y-0 right-1/2 bg-emerald-500/70"
            style={{ width: `${homePct / 2}%` }}
          />
        )}
        {awayLeans && (
          <div
            className="absolute inset-y-0 left-1/2 bg-orange-500/70"
            style={{ width: `${awayPct / 2}%` }}
          />
        )}
      </div>
      <div className="text-right tabular-nums text-slate-500">
        <span className={homeLeans ? "text-emerald-400" : "text-slate-700"}>
          {formatPct(row.homeShift)}
        </span>
        <span className="text-slate-700 mx-1">/</span>
        <span className={awayLeans ? "text-orange-400" : "text-slate-700"}>
          {formatPct(row.awayShift)}
        </span>
      </div>
    </div>
  )
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
