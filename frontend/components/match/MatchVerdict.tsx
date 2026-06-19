import type { MatchPrediction } from "@/lib/types"
import { ConfidenceChip, confidenceFromProbs } from "@/components/common/ConfidenceChip"

/** Plain-language read of the model's numbers, so a non-expert gets a decision, not a
 *  wall of probabilities. Everything here is derived from the same prediction. */
export function MatchVerdict({
  p, homeName, awayName,
}: { p: MatchPrediction; homeName: string; awayName: string }) {
  const confidence = confidenceFromProbs(p.home_win, p.draw, p.away_win)
  const lines: { label: string; text: string; tone: "pos" | "warn" | "neutral" }[] = []

  // Who's favoured
  const opts = [
    { name: homeName, v: p.home_win, kind: "home" },
    { name: "a draw", v: p.draw, kind: "draw" },
    { name: awayName, v: p.away_win, kind: "away" },
  ].sort((a, b) => b.v - a.v)
  const fav = opts[0]
  const favPct = Math.round(fav.v * 100)
  if (fav.kind === "draw") {
    lines.push({ label: "Result", text: `Too close to call. A draw is the single most likely outcome at ${favPct}%.`, tone: "warn" })
  } else if (fav.v >= 0.6) {
    lines.push({ label: "Result", text: `${fav.name} are strong favourites at ${favPct}%.`, tone: "pos" })
  } else if (fav.v >= 0.45) {
    lines.push({ label: "Result", text: `${fav.name} are slight favourites at ${favPct}%, but it is far from settled.`, tone: "neutral" })
  } else {
    lines.push({ label: "Result", text: `An open match. ${fav.name} edge it at just ${favPct}%.`, tone: "warn" })
  }

  // Goals
  const over = Math.round(p.over_2_5 * 100)
  if (p.over_2_5 >= 0.56) {
    lines.push({ label: "Goals", text: `Goals expected. Over 2.5 lands ${over}% of the time.`, tone: "pos" })
  } else if (p.over_2_5 <= 0.44) {
    lines.push({ label: "Goals", text: `A low-scoring game looks likely. Under 2.5 is favoured (${100 - over}%).`, tone: "pos" })
  } else {
    lines.push({ label: "Goals", text: `Goals are a coin-flip around the 2.5 line (over ${over}%).`, tone: "neutral" })
  }

  // BTTS
  const btts = Math.round(p.btts * 100)
  if (p.btts >= 0.56) lines.push({ label: "Both score", text: `Both teams to score is likely (${btts}%).`, tone: "pos" })
  else if (p.btts <= 0.44) lines.push({ label: "Both score", text: `Expect at least one clean sheet. Both-teams-score is just ${btts}%.`, tone: "pos" })

  const topScore = p.top_scores?.[0]
  const value = p.markets?.filter((m) => m.is_positive_ev).sort((a, b) => b.ev - a.ev)[0]

  const dot = { pos: "bg-emerald-400", warn: "bg-amber-400", neutral: "bg-slate-500" }

  return (
    <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/[0.04] p-4 sm:p-5">
      <div className="flex items-center justify-between mb-3 gap-2">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/90">The model&apos;s read</p>
        <ConfidenceChip level={confidence} />
      </div>
      <ul className="space-y-2.5">
        {lines.map((l, i) => (
          <li key={i} className="flex gap-2.5">
            <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${dot[l.tone]}`} />
            <p className="text-[13px] text-slate-200 leading-snug">
              <span className="text-slate-500 font-semibold">{l.label}: </span>{l.text}
            </p>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2 mt-4">
        {topScore && (
          <span className="text-[12px] rounded-lg bg-surface-3 border border-edge px-3 py-1.5 text-slate-300">
            Most likely score <span className="font-mono font-bold text-white">{topScore.home}&ndash;{topScore.away}</span>
            <span className="text-slate-500"> ({Math.round(topScore.probability * 100)}%)</span>
          </span>
        )}
        {value && (
          <span className="text-[12px] rounded-lg bg-emerald-950/40 border border-emerald-800/50 px-3 py-1.5 text-emerald-300">
            Best value <span className="font-semibold text-white">{value.label}</span>
            <span className="text-emerald-400/80"> at {value.bookmaker_odds.toFixed(2)}</span>
          </span>
        )}
      </div>
    </div>
  )
}
