import type { MatchPrediction } from "@/lib/types"

/**
 * Data provenance — a one-line "where these numbers came from + how fresh"
 * footer under the prediction. Builds trust: the reader can see we're pricing
 * off a sharp line, how much xG history backs the teams, and the squad-value
 * source. Everything here is already in the prediction payload; nothing new is
 * fetched. Renders nothing when there's genuinely nothing to show.
 */
export function DataProvenance({ p }: { p: MatchPrediction }) {
  const bits: string[] = []

  // Odds source — sharp (Pinnacle) is the strongest anchor; "estimated" means
  // no real book line yet, which the reader deserves to know.
  const src = p.odds_source
  if (src === "sharp+live" || src === "sharp") bits.push("Priced vs sharp (Pinnacle) line")
  else if (src === "live") bits.push("Priced vs bookmaker line")
  else if (src === "estimated") bits.push("No live odds yet — model-only")

  // xG sample backing each side (from the harvested archive).
  const hx = p.context?.harvested?.home?.xg_sample
  const ax = p.context?.harvested?.away?.xg_sample
  const samples = [hx, ax].filter((n): n is number => typeof n === "number" && n > 0)
  if (samples.length === 2) bits.push(`xG over last ${Math.min(hx!, ax!)}-${Math.max(hx!, ax!)} games`)
  else if (samples.length === 1) bits.push(`xG sample: ${samples[0]} games`)

  // Squad-value provenance — constant, but states the licensed source.
  bits.push("squad values: Rising Transfers")

  // Model-uncertainty caveat — when our ELO and DC views disagree, say so.
  const unc = p.model_uncertainty
  const uncText =
    unc === "uncertain" ? "our ratings disagree here — lower confidence"
    : unc === "moderate" ? "some rating disagreement — medium confidence"
    : null

  if (bits.length === 0 && !uncText) return null

  return (
    <p className="text-[10px] text-slate-600 leading-relaxed mt-2 flex flex-wrap items-center gap-x-1.5">
      <span className="inline-block w-1 h-1 rounded-full bg-slate-700 shrink-0" />
      {bits.map((b, i) => (
        <span key={i}>
          {b}
          {(i < bits.length - 1 || uncText) && <span className="text-slate-700"> ·</span>}
        </span>
      ))}
      {uncText && <span className={unc === "uncertain" ? "text-amber-400/80" : "text-slate-500"}>{uncText}</span>}
    </p>
  )
}
