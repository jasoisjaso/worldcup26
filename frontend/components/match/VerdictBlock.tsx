import type { MatchPrediction, Match, Market } from "@/lib/types"

/**
 * Verdict block. Layer 1 of the /match taste pass.
 *
 * Plain-English verdict for a casual punter, not a quant. Reads in 5
 * seconds: "is there a bet here, on what, how much should I risk?"
 *
 * Key design choices vs the first attempt:
 *
 * 1. The pick is the HIGHEST-EDGE 1X2 outcome, not the model's top
 *    probability. Locking onto the favourite produced "Avoid Bosnia"
 *    when Bosnia were the fair-priced 75% favourite. Reads as
 *    "Bosnia are bad" which is wrong. The right sentence is "no edge
 *    here, bookies got Bosnia priced right".
 *
 * 2. Voice bands map to one of three sentences a sharp friend would
 *    say. No "pt", no "fair price", no "Kelly" jargon. The stake is
 *    rendered in dollars on a hypothetical $1000 bankroll so a
 *    casual immediately gets the scale.
 *
 * 3. The picked outcome's tile in the odds strip is highlighted so
 *    the eye can pair the verdict sentence with which odds it refers
 *    to without re-reading.
 */

type Side = "home" | "draw" | "away"

interface Candidate {
  side: Side
  label: string
  modelProb: number
  marketImplied: number
  bookOdds: number
  reliability: Market["reliability"] | null
  edgePct: number   // (model/implied - 1) * 100, the relative band driver
  edgePts: number   // (model - implied) * 100, used in the copy
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
  // Best CANDIDATE PICK is highest positive edge, ignoring longshot reliability
  // (longshot edges are the +68% EV failure mode we explicitly de-publish).
  const eligible = candidates.filter((c) => c.reliability !== "longshot")
  const sorted = [...eligible].sort((a, b) => b.edgePct - a.edgePct)
  const best = sorted[0] ?? null

  // Bands require BOTH a relative edge (so a tiny price disagreement on a
  // big favourite doesn't count) AND an absolute point delta (so an 8%
  // relative edge on a 25% draw, only 2pt absolute, doesn't sound
  // "meaningful" to a casual reader). The absolute floor matches how a
  // punter mentally tallies "the model thinks this is X points higher
  // than the bookies".
  if (!best) return { pick: null, band: "no-edge" }
  if (best.edgePct >= 8 && best.edgePts >= 5) return { pick: best, band: "strong" }
  if (best.edgePct >= 4 && best.edgePts >= 2) return { pick: best, band: "lean" }
  return { pick: null, band: "no-edge" }
}

function odds(p: MatchPrediction, market: Market["market"]): number | null {
  const m = (p.markets ?? []).find((mk) => mk.market === market)
  return m?.bookmaker_odds ?? null
}

// Quarter-Kelly inline. Same maths as singles in the picker. We render the
// dollar figure on a $1000 bankroll because that's the unit casual punters
// translate "stake" into. Skill-bet sites speak in units; we speak in dollars.
function quarterKellyDollars(modelProb: number, bookOdds: number, bankroll = 1000): number | null {
  if (bookOdds <= 1 || modelProb <= 0) return null
  const b = bookOdds - 1
  const q = 1 - modelProb
  const full = (modelProb * b - q) / b
  if (full <= 0) return null
  const fraction = full / 4
  // Cap at 5% of bankroll. Even a quarter Kelly can blow up on a fluke big
  // edge that turns out to be a model error. Casual punter protection.
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
  headline: string        // hero sentence, first thing the eye lands on
  explain: string         // one-sentence explanation in plain English
  ringClass: string
  badgeClass: string
}

function copyForBand(
  band: Band, pick: Candidate | null, p: MatchPrediction, m: Match,
): VerdictCopy {
  if (band === "strong" && pick) {
    const subject = pick.side === "draw" ? "the draw" : pick.label
    return {
      badge: "Take it",
      // "Too long" means bookie offering a longer price than fair, which is good
      // for us to back. ("Too short" would mean the OPPOSITE.)
      headline: `Bookies are too long on ${subject}.`,
      explain: `Model thinks ${subject} ${pick.side === "draw" ? "lands" : "wins"} ${Math.round(pick.modelProb * 100)}% of the time, but the bookies are pricing it like ${Math.round(pick.marketImplied * 100)}%. That's a ${Math.abs(pick.edgePts).toFixed(0)}-point gap, worth a bet at this price.`,
      ringClass: "ring-emerald-500/40 border-emerald-700/40 bg-emerald-950/30",
      badgeClass: "bg-emerald-500/20 text-emerald-300",
    }
  }
  if (band === "lean" && pick) {
    const subject = pick.side === "draw" ? "the draw" : pick.label
    return {
      badge: "Small lean",
      headline: `Slight lean towards ${subject}.`,
      explain: `Model rates ${subject} a touch higher than the bookies do (${Math.round(pick.modelProb * 100)}% vs ${Math.round(pick.marketImplied * 100)}%). Real but small, so keep the stake light.`,
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

/**
 * Single odds tile. The picked tile gets a brighter edge so the eye pairs
 * the verdict sentence with which outcome it refers to. Non-picked tiles
 * keep the slate base so we don't have three competing colour weights.
 */
function OddsTile({
  label, price, highlighted,
}: {
  label: string
  price: number | null
  highlighted: boolean
}) {
  return (
    <div className={[
      "rounded-lg border px-2 py-2",
      highlighted
        ? "bg-emerald-950/30 border-emerald-700/50"
        : "bg-surface-1 border-edge",
    ].join(" ")}>
      <p className="text-[9px] uppercase tracking-widest text-slate-600 truncate">{label}</p>
      <p className={[
        "text-[18px] font-bold font-mono tabular-nums",
        highlighted ? "text-emerald-300" : "text-slate-100",
      ].join(" ")}>
        {price ? `$${price.toFixed(2)}` : "..."}
      </p>
    </div>
  )
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
  const pickedSide = pick?.side ?? null

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

      {/* 1X2 odds strip. The picked tile is highlighted so the eye pairs the
          verdict sentence to which outcome it refers to without re-reading. */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-center">
        <OddsTile label={match.home.name} price={homeOdds} highlighted={pickedSide === "home"} />
        <OddsTile label="Draw"             price={drawOdds} highlighted={pickedSide === "draw"} />
        <OddsTile label={match.away.name} price={awayOdds} highlighted={pickedSide === "away"} />
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

      {/* "How to play it" only shows when there's actually a pick. Dollars on a
          $1000 bankroll so the scale lands without a Kelly explainer. */}
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
