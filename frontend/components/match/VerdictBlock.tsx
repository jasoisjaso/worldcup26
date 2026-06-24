import type { MatchPrediction, Match, Market } from "@/lib/types"

/**
 * Verdict block — Layer 1 of the /match taste pass.
 *
 * Plain-English verdict for a casual punter, not a quant. Reads in 5
 * seconds: "is there a bet here, on what, how much should I risk?"
 *
 * Key design choices vs the first attempt:
 *
 * 1. The pick is the HIGHEST-EDGE 1X2 outcome, not the model's top
 *    probability. Locking onto the favourite produced "Avoid Bosnia"
 *    when Bosnia were the fair-priced 75% favourite — technically
 *    correct (no edge) but reads as "Bosnia are bad". The right
 *    sentence is "no edge here, bookies got Bosnia priced right".
 *
 * 2. Voice bands map to one of four sentences a sharp friend would
 *    say. No "pt", no "fair price", no "¼-Kelly" jargon. The stake
 *    is rendered in dollars on a hypothetical $1000 bankroll so a
 *    casual immediately gets the scale.
 *
 * 3. "Stay away" is reserved for the rare case where the model
 *    disagrees with the bookies' choice of favourite. In every other
 *    no-edge case we say "no clear edge" — honest, not scary.
 */

type Side = "home" | "draw" | "away"

interface Candidate {
  side: Side
  label: string
  modelProb: number
  marketImplied: number
  bookOdds: number
  reliability: Market["reliability"] | null
  edgePct: number   // (model/implied - 1) * 100 — the verdict band driver
  edgePts: number   // (model - implied) * 100 — used in plain-English copy
}

function buildCandidates(p: MatchPrediction, m: Match): Candidate[] {
  const out: Candidate[] = []
  const seeds: { side: Side; label: string; modelProb: number; market: Market["market"] }[] = [
    { side: "home", label: m.home.name, modelProb: p.home_win, market: "home_win" },
    { side: "draw", label: "the draw",   modelProb: p.draw,     market: "draw" },
    { side: "away", label: m.away.name, modelProb: p.away_win, market: "away_win" },
  ]
  for (const s of seeds) {
    const mkt = (p.markets ?? []).find((mk) => mk.market === s.market)
    const implied = mkt?.market_implied ?? (mkt?.bookmaker_odds ? 1 / mkt.bookmaker_odds : null)
    if (!implied || !mkt?.bookmaker_odds || implied <= 0) continue
    out.push({
      side: s.side,
      label: s.label,
      modelProb: s.modelProb,
      marketImplied: implied,
      bookOdds: mkt.bookmaker_odds,
      reliability: mkt.reliability ?? null,
      edgePct: (s.modelProb / implied - 1) * 100,
      edgePts: (s.modelProb - implied) * 100,
    })
  }
  return out
}

type Band = "strong" | "lean" | "no-edge"

function pickAndBand(candidates: Candidate[]): { pick: Candidate | null; band: Band } {
  // Best CANDIDATE PICK = highest positive edge, ignoring longshot reliability
  // (longshot edges are the +68% EV failure mode we explicitly de-publish).
  const eligible = candidates.filter((c) => c.reliability !== "longshot")
  const sorted = [...eligible].sort((a, b) => b.edgePct - a.edgePct)
  const best = sorted[0] ?? null

  if (!best || best.edgePct < 3) return { pick: null, band: "no-edge" }
  if (best.edgePct >= 8) return { pick: best, band: "strong" }
  return { pick: best, band: "lean" }
}

function odds(p: MatchPrediction, market: Market["market"]): number | null {
  const m = (p.markets ?? []).find((mk) => mk.market === market)
  return m?.bookmaker_odds ?? null
}

function decimalToAmerican(o: number | null): string {
  if (!o || o <= 1) return "—"
  if (o >= 2) return `+${Math.round((o - 1) * 100)}`
  return `-${Math.round(100 / (o - 1))}`
}

// Quarter-Kelly inline — same maths as singles in the picker. We render the
// dollar figure on a $1000 bankroll because that's the unit casual punters
// translate "stake" into. Skill-bet sites speak in units; we speak in dollars.
function quarterKellyDollars(modelProb: number, bookOdds: number, bankroll = 1000): number | null {
  if (bookOdds <= 1 || modelProb <= 0) return null
  const b = bookOdds - 1
  const q = 1 - modelProb
  const full = (modelProb * b - q) / b
  if (full <= 0) return null
  const fraction = full / 4
  // Cap at 5% of bankroll — even a quarter Kelly can blow up on a fluke big edge
  // that turns out to be a model error. Casual punter protection.
  return Math.min(fraction, 0.05) * bankroll
}

function favouriteName(p: MatchPrediction, m: Match): { name: string; pct: number } {
  const opts: { name: string; pct: number }[] = [
    { name: m.home.name, pct: p.home_win * 100 },
    { name: "a draw",     pct: p.draw * 100 },
    { name: m.away.name, pct: p.away_win * 100 },
  ]
  opts.sort((a, b) => b.pct - a.pct)
  return opts[0]
}

interface VerdictCopy {
  badge: string
  headline: string        // hero sentence — first thing the eye lands on
  explain: string         // one-sentence explanation in plain English
  ringClass: string
  badgeClass: string
}

function copyForBand(
  band: Band, pick: Candidate | null, p: MatchPrediction, m: Match,
): VerdictCopy {
  if (band === "strong" && pick) {
    return {
      badge: "Take it",
      headline: pick.side === "draw"
        ? "Bookies are too short on the draw."
        : `Bookies are too long on ${pick.label}.`,
      explain: `Model rates ${pick.side === "draw" ? "the draw" : pick.label} ${Math.abs(pick.edgePts).toFixed(0)} points higher than the bookies — a meaningful gap.`,
      ringClass: "ring-emerald-500/40 border-emerald-700/40 bg-emerald-950/30",
      badgeClass: "bg-emerald-500/20 text-emerald-300",
    }
  }
  if (band === "lean" && pick) {
    return {
      badge: "Small lean",
      headline: pick.side === "draw"
        ? "Slight lean towards the draw."
        : `Slight lean towards ${pick.label}.`,
      explain: `Model has ${pick.side === "draw" ? "the draw" : pick.label} a few points ahead of the bookies. Real but small — keep the stake light.`,
      ringClass: "ring-emerald-700/20 border-emerald-900/40 bg-emerald-950/15",
      badgeClass: "bg-emerald-700/20 text-emerald-300",
    }
  }
  // no-edge
  const fav = favouriteName(p, m)
  return {
    badge: "No bet",
    headline: "No clear edge in this match.",
    explain: `Bookies have ${fav.name} as the favourite at ${Math.round(fav.pct)}% and the model agrees. Save the stake for a match we actually disagree on.`,
    ringClass: "ring-slate-700/30 border-edge bg-surface-2",
    badgeClass: "bg-slate-700/30 text-slate-300",
  }
}

export function VerdictBlock({
  prediction,
  match,
  complete,
}: {
  prediction: MatchPrediction
  match: Match
  complete: boolean
}) {
  if (complete) return null

  const candidates = buildCandidates(prediction, match)
  const { pick, band } = pickAndBand(candidates)
  const copy = copyForBand(band, pick, prediction, match)

  const homeOdds = odds(prediction, "home_win")
  const drawOdds = odds(prediction, "draw")
  const awayOdds = odds(prediction, "away_win")

  const dollar = pick ? quarterKellyDollars(pick.modelProb, pick.bookOdds, 1000) : null

  return (
    <div className={`rounded-2xl border shadow-e1 p-5 mb-5 ring-1 ${copy.ringClass}`}>
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <span className={`text-[10px] font-bold uppercase tracking-[0.18em] px-2 py-0.5 rounded ${copy.badgeClass}`}>
          {copy.badge}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
          The model&apos;s read
        </span>
      </div>

      {/* 1X2 odds strip — both Australian/decimal (the punter format here) and
          American so US visitors recognise it. Tabular nums for alignment. */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-center">
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600 truncate">{match.home.name}</p>
          <p className="text-[18px] font-bold font-mono tabular-nums text-slate-100">{homeOdds ? `$${homeOdds.toFixed(2)}` : "—"}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{decimalToAmerican(homeOdds)}</p>
        </div>
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600">Draw</p>
          <p className="text-[18px] font-bold font-mono tabular-nums text-slate-100">{drawOdds ? `$${drawOdds.toFixed(2)}` : "—"}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{decimalToAmerican(drawOdds)}</p>
        </div>
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600 truncate">{match.away.name}</p>
          <p className="text-[18px] font-bold font-mono tabular-nums text-slate-100">{awayOdds ? `$${awayOdds.toFixed(2)}` : "—"}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{decimalToAmerican(awayOdds)}</p>
        </div>
      </div>

      {/* Headline + plain-English explanation. Headline is the verdict in one
          sentence; explanation translates the numbers. Together they replace
          the old "Edge / Fair price / Kelly" jargon row. */}
      <p className="text-[18px] sm:text-[20px] font-bold text-slate-100 leading-snug mb-2">
        {copy.headline}
      </p>
      <p className="text-[13px] text-slate-300 leading-relaxed mb-3">
        {copy.explain}
      </p>

      {/* "How to play it" — only when there's actually a pick. Dollars on a $1000
          bankroll so the scale lands without a Kelly explainer. */}
      {pick && dollar != null && (
        <div className="pt-3 border-t border-edge/40">
          <p className="text-[9px] uppercase tracking-widest text-slate-600 mb-1">
            How to play it
          </p>
          <p className="text-[13px] text-slate-200 leading-relaxed">
            Stake around{" "}
            <span className="font-bold font-mono tabular-nums text-slate-100">${dollar.toFixed(0)}</span>
            {" "}on a $1,000 bankroll{" "}
            <span className="text-slate-500">(scale the same way for yours).</span>
            {" "}Take any price{" "}
            <span className="font-bold font-mono tabular-nums text-slate-100">${pick.bookOdds.toFixed(2)}</span>
            {" "}or longer.
          </p>
        </div>
      )}
    </div>
  )
}
