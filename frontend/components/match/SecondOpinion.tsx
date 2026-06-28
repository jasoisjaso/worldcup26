import type { MatchPrediction } from "@/lib/types"

interface Props {
  prediction: MatchPrediction
  homeName: string
  awayName: string
}

/**
 * "Two-model view": shows api-football's own AI prediction alongside ours,
 * with an agreement score. We expose this for transparency only — their
 * model is NOT blended into our lambda (different architecture, no offline
 * backtest yet to justify ensembling).
 *
 * Renders null when api-football has no prediction for the fixture (the
 * harvest backlog may not have processed their /predictions blob yet).
 */
export function SecondOpinion({ prediction, homeName, awayName }: Props) {
  const af = prediction.api_football
  if (!af) return null
  const p = af.prediction
  const a = af.agreement

  const tone = a.label === "consensus"
    ? "border-emerald-500/30 bg-emerald-950/30 text-emerald-300"
    : a.label === "moderate"
    ? "border-amber-500/30 bg-amber-950/30 text-amber-300"
    : "border-rose-500/30 bg-rose-950/30 text-rose-300"

  const labelCopy = a.label === "consensus"
    ? "Two-model consensus"
    : a.label === "moderate"
    ? "Two models moderately agree"
    : "Two models diverge"

  return (
    <div className="mb-5">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">
        Two-model view
      </p>
      <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5">
        <div className="flex items-center justify-between gap-3 mb-3">
          <p className="text-[12px] text-slate-300">
            <span className="text-slate-500">Second model</span>{" "}
            <span className="font-mono text-slate-400">api-football</span>
          </p>
          <span className={`text-[10px] font-bold uppercase tracking-widest rounded-md border px-2 py-1 ${tone}`}>
            {labelCopy}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2 mb-3">
          <ProbCell label={homeName} value={p.home_win} />
          <ProbCell label="Draw" value={p.draw} />
          <ProbCell label={awayName} value={p.away_win} />
        </div>

        {p.comparison?.att && p.comparison?.def && (
          <div className="border-t border-edge pt-3 mt-1">
            <p className="text-[9px] font-bold uppercase tracking-widest text-slate-600 mb-2">
              Their internal ratings (0-100)
            </p>
            <ComparisonRow label="Form"    pair={p.comparison.form} home={homeName} away={awayName} />
            <ComparisonRow label="Attack"  pair={p.comparison.att}  home={homeName} away={awayName} />
            <ComparisonRow label="Defence" pair={p.comparison.def}  home={homeName} away={awayName} />
          </div>
        )}

        {p.advice && (
          <p className="text-[11px] text-slate-500 italic mt-3 leading-snug">
            Their advice: <span className="text-slate-300">{p.advice}</span>
          </p>
        )}

        <p className="text-[10px] text-slate-600 mt-3 leading-snug">
          Surfaced for transparency. We don&apos;t blend api-football&apos;s
          numbers into our model — a second opinion, not a vote.
        </p>
      </div>
    </div>
  )
}

function ProbCell({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-lg border border-edge bg-surface-3 px-2 py-2 text-center">
      <p className="text-[10px] text-slate-500 truncate mb-1">{label}</p>
      <p className="font-display font-bold text-[20px] tabular-nums text-ink leading-none">
        {Math.round(value * 100)}
        <span className="text-slate-600 text-[12px] font-medium">%</span>
      </p>
    </div>
  )
}

function ComparisonRow({
  label,
  pair,
  home,
  away,
}: {
  label: string
  pair: [number, number] | null | undefined
  home: string
  away: string
}) {
  if (!pair) return null
  const [h, a] = pair
  // Both numbers are 0..1 (converted from "67%" → 0.67 in the backend). Render
  // as 0..100 here for readability.
  const hPct = Math.round(h * 100)
  const aPct = Math.round(a * 100)
  return (
    <div className="grid grid-cols-[1fr_60px_1fr] items-center gap-2 mb-1 text-[10px]">
      <div className="text-right tabular-nums">
        <span className={hPct > aPct ? "text-emerald-300 font-bold" : "text-slate-500"}>{hPct}</span>
        <span className="text-slate-700 ml-1 text-[9px]" title={home}>·</span>
      </div>
      <div className="text-center text-slate-600 text-[9px] uppercase tracking-widest">{label}</div>
      <div className="text-left tabular-nums">
        <span className="text-slate-700 mr-1 text-[9px]" title={away}>·</span>
        <span className={aPct > hPct ? "text-orange-300 font-bold" : "text-slate-500"}>{aPct}</span>
      </div>
    </div>
  )
}
