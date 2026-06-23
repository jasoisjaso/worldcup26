"use client"
/**
 * Pick Performance — the bottom-line "is the model winning money" tile.
 *
 * Reads /admin/pick-performance which computes rolling 30d unit-stake P&L
 * over logged picks (Prediction table joined to settled Match rows). Voids
 * from interrupted matches are excluded so the ROI number stays honest.
 *
 * Shows three layers:
 *   1. Top KPIs: hit rate / profit / ROI / sample size / average CLV
 *   2. By market — which markets are carrying / dragging the P&L
 *   3. By confidence band — are our 60-80% picks landing at 60-80% rate?
 *
 * CLV (closing-line value) row is the leading indicator: positive CLV with
 * sub-zero ROI means edge is real but sample is small; positive ROI without
 * CLV means we got lucky.
 */
import { Section, Kpi, fmt, fmtPct, fmtPctSigned, type KpiColor } from "@/components/admin/parts"

interface Bucket { n: number; wins: number; hit_rate: number | null; profit_u: number; roi: number | null }
interface PickPerf {
  window_days: number
  total: Bucket & { stake_u: number }
  clv: { n: number; avg: number | null }
  by_market: Record<string, Bucket>
  by_confidence: Record<string, Bucket>
}

function colorFor(profit_u: number, n: number): KpiColor {
  if (n < 10) return "neutral"  // too few picks to colour
  if (profit_u > 0) return "green"
  if (profit_u < 0) return "red"
  return "neutral"
}

export function PickPerformance({ data }: { data: PickPerf | null }) {
  if (!data) {
    return (
      <Section title="Pick Performance" subtitle="Loading">
        <p className="text-[11px] text-slate-600">Computing 30d rolling unit P&amp;L…</p>
      </Section>
    )
  }
  const t = data.total
  const subtitle = `${data.window_days}d window · ${fmt(t.n)} settled picks (voids excluded)`

  return (
    <Section title="Pick Performance" subtitle={subtitle}>
      {t.n === 0 ? (
        <p className="text-[11px] text-slate-600">
          No settled picks in the last {data.window_days}d. Tile populates after MD1 results land.
        </p>
      ) : (
        <div className="space-y-4">
          {/* Top KPIs */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Kpi
              label="Hit rate"
              value={fmtPct(t.hit_rate, 1)}
              sub={`${fmt(t.wins)} of ${fmt(t.n)}`}
              color="neutral"
            />
            <Kpi
              label="ROI / pick"
              value={fmtPctSigned(t.roi, 1)}
              sub={`${t.profit_u >= 0 ? "+" : ""}${t.profit_u.toFixed(2)}u total`}
              color={colorFor(t.profit_u, t.n)}
            />
            <Kpi
              label="CLV avg"
              value={data.clv.avg == null ? "—" : fmtPctSigned(data.clv.avg, 2)}
              sub={`${fmt(data.clv.n)} with closing`}
              color={data.clv.avg == null ? "neutral" : data.clv.avg > 0 ? "green" : "red"}
            />
            <Kpi
              label="Sample"
              value={fmt(t.n)}
              sub={t.n < 30 ? "small — treat ROI as noise" : "actionable"}
              color={t.n < 30 ? "amber" : "neutral"}
            />
          </div>

          {/* By market */}
          <BucketTable
            title="By market"
            buckets={data.by_market}
            highlight="profit"
          />

          {/* By confidence */}
          <BucketTable
            title="By confidence band (model probability)"
            buckets={data.by_confidence}
            highlight="hit_rate"
            note="Hit rate should roughly match the band — 60-80% band landing at 65% is well-calibrated."
          />
        </div>
      )}
    </Section>
  )
}

function BucketTable({
  title, buckets, highlight, note,
}: {
  title: string
  buckets: Record<string, Bucket>
  highlight: "profit" | "hit_rate"
  note?: string
}) {
  const entries = Object.entries(buckets)
  if (entries.length === 0) return null
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-1.5">{title}</p>
      {note && <p className="text-[10px] text-slate-600 mb-2">{note}</p>}
      <div className="border border-edge bg-surface-2 rounded-lg divide-y divide-edge/40">
        {entries.map(([key, b]) => {
          const profitColor = b.n < 10 ? "text-slate-500"
            : b.profit_u > 0 ? "text-emerald-300"
            : b.profit_u < 0 ? "text-rose-400"
            : "text-slate-300"
          const hitColor = highlight === "hit_rate" ? "text-amber-300 font-bold" : "text-slate-300"
          return (
            <div key={key} className="flex items-center gap-3 px-3 py-1.5 text-[11px] font-mono tabular-nums">
              <span className="text-slate-300 flex-1 truncate">{key}</span>
              <span className="text-slate-500 w-12 text-right">n {fmt(b.n)}</span>
              <span className={`w-14 text-right ${hitColor}`}>{fmtPct(b.hit_rate, 0)}</span>
              <span className={`w-20 text-right ${profitColor} font-bold`}>
                {b.profit_u >= 0 ? "+" : ""}{b.profit_u.toFixed(2)}u
              </span>
              <span className={`w-16 text-right ${profitColor}`}>{fmtPctSigned(b.roi, 1)}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
