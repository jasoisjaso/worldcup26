import type { MatchPrediction, Match, Market } from "@/lib/types"

/**
 * Verdict block — Layer 1 of the /match taste pass.
 *
 * One sentence that tells the punter what the model thinks, why, and how
 * much to stake. Everything else on the page is supporting evidence; if
 * the reader trusts our earlier picks, they're done here in 5 seconds.
 *
 * Voice rules (from the research doc):
 *   - edge band > +8%   → confident, brief    ("Strong back …")
 *   - edge band +3..+8% → measured             ("Lean …")
 *   - edge band -3..+3% → honest               ("Pass — fair pricing")
 *   - edge band < -3%   → contrarian           ("Avoid — overpriced")
 *
 * No "Predicted/Forecasted" verbs, no exclamation marks, no ALL CAPS for
 * emphasis. Stake printed in units (Kelly fraction the backend already
 * computed). Fair price rounded to 2dp.
 */

type Side = "home" | "draw" | "away"

interface PickRead {
  side: Side
  label: string         // team name or "Draw"
  modelProb: number     // calibrated display number
  marketImplied: number | null
  bookOdds: number | null
  fairOdds: number | null
  edgePts: number       // (model - implied) * 100
  edgePct: number       // (model/implied - 1) * 100 — relative, the verdict band
  reliability: Market["reliability"] | null
  kellyPct: number | null
}

function pickFromPrediction(p: MatchPrediction, m: Match): PickRead {
  // Whichever 1X2 outcome carries the most model probability is "the pick".
  // We deliberately treat a draw as a valid pick — if the model thinks a draw
  // is the single most likely outcome we should say so, not paper over it.
  const opts: { side: Side; label: string; prob: number; market: Market["market"] }[] = [
    { side: "home", label: m.home.name, prob: p.home_win, market: "home_win" },
    { side: "draw", label: "Draw",       prob: p.draw,     market: "draw" },
    { side: "away", label: m.away.name, prob: p.away_win, market: "away_win" },
  ]
  opts.sort((a, b) => b.prob - a.prob)
  const top = opts[0]
  const mkt = (p.markets ?? []).find((mk) => mk.market === top.market)
  const marketImplied = mkt?.market_implied ?? (mkt?.bookmaker_odds ? 1 / mkt.bookmaker_odds : null)
  const edgePts = marketImplied ? (top.prob - marketImplied) * 100 : 0
  const edgePct = marketImplied && marketImplied > 0 ? (top.prob / marketImplied - 1) * 100 : 0

  // Quarter-Kelly inline — keeps the verdict block self-contained and means
  // we recompute against THIS pick's prob/odds rather than whatever the
  // backend logged at snapshot time. Full-Kelly f = (pb - q) / b where
  // b = odds - 1, q = 1 - p. Quarter that for conservative real-money sizing.
  let kellyPct: number | null = null
  if (mkt?.bookmaker_odds && mkt.bookmaker_odds > 1 && top.prob > 0) {
    const b = mkt.bookmaker_odds - 1
    const q = 1 - top.prob
    const full = (top.prob * b - q) / b
    if (full > 0) kellyPct = (full / 4) * 100
  }

  return {
    side: top.side,
    label: top.label,
    modelProb: top.prob,
    marketImplied,
    bookOdds: mkt?.bookmaker_odds ?? null,
    fairOdds: top.prob > 0 ? 1 / top.prob : null,
    edgePts,
    edgePct,
    reliability: mkt?.reliability ?? null,
    kellyPct,
  }
}

type VerdictBand = "strong" | "lean" | "pass" | "avoid"

function bandFromEdge(edgePct: number, reliability: Market["reliability"] | null): VerdictBand {
  // The model can only "see value" when its disagreement with the market is
  // believable. A longshot ratio + a glowing edge is the +68% EV failure mode;
  // we explicitly demote those to PASS so the verdict line stays honest.
  if (reliability === "longshot") return "pass"
  if (edgePct >= 8) return "strong"
  if (edgePct >= 3) return "lean"
  if (edgePct >= -3) return "pass"
  return "avoid"
}

function verdictLine(p: PickRead, band: VerdictBand): string {
  const edgeStr = Math.abs(p.edgePct).toFixed(1) + "%"
  if (band === "strong") {
    return p.side === "draw"
      ? `Strong draw — model has it ${edgeStr} shorter than fair.`
      : `Strong back ${p.label} — model has them ${edgeStr} shorter than fair.`
  }
  if (band === "lean") {
    return p.side === "draw"
      ? `Lean draw — small edge, sample is modest.`
      : `Lean ${p.label} — small edge, sample is modest.`
  }
  if (band === "pass") {
    return `Pass — fair pricing, no clear edge here.`
  }
  return p.side === "draw"
    ? `Avoid the draw — market sees something the model doesn't.`
    : `Avoid ${p.label} — overpriced. Market sees something the model doesn't.`
}

function bandStyle(band: VerdictBand) {
  if (band === "strong") return {
    badge: "Strong back",
    ring: "ring-emerald-500/40 border-emerald-700/40 bg-emerald-950/30",
    badgeBg: "bg-emerald-500/20 text-emerald-300",
    edgeTone: "text-emerald-300",
  }
  if (band === "lean") return {
    badge: "Lean",
    ring: "ring-emerald-700/20 border-emerald-900/40 bg-emerald-950/15",
    badgeBg: "bg-emerald-700/20 text-emerald-300",
    edgeTone: "text-emerald-300",
  }
  if (band === "pass") return {
    badge: "Pass",
    ring: "ring-slate-700/30 border-edge bg-surface-2",
    badgeBg: "bg-slate-700/30 text-slate-300",
    edgeTone: "text-slate-400",
  }
  return {
    badge: "Avoid",
    ring: "ring-amber-700/30 border-amber-900/40 bg-amber-950/20",
    badgeBg: "bg-amber-500/15 text-amber-300",
    edgeTone: "text-rose-300",
  }
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

export function VerdictBlock({
  prediction,
  match,
  complete,
}: {
  prediction: MatchPrediction
  match: Match
  complete: boolean
}) {
  // Suppress on complete matches — there is no decision to make any more.
  // The recap block above handles "what happened" coverage.
  if (complete) return null

  const pick = pickFromPrediction(prediction, match)
  const band = bandFromEdge(pick.edgePct, pick.reliability)
  const s = bandStyle(band)
  const line = verdictLine(pick, band)

  const homeOdds = odds(prediction, "home_win")
  const drawOdds = odds(prediction, "draw")
  const awayOdds = odds(prediction, "away_win")

  return (
    <div className={`rounded-2xl border shadow-e1 p-5 mb-5 ring-1 ${s.ring}`}>
      <div className="flex items-baseline justify-between gap-2 mb-3">
        <span className={`text-[9px] font-bold uppercase tracking-[0.18em] px-2 py-0.5 rounded ${s.badgeBg}`}>
          {s.badge}
        </span>
        <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
          The model's read
        </span>
      </div>

      {/* 1X2 odds strip — American odds + decimal, mirrors how Apple Sports
          renders a pre-game line. Tabular nums so vertical alignment holds. */}
      <div className="grid grid-cols-3 gap-2 mb-4 text-center">
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600 truncate">{match.home.name}</p>
          <p className="text-[15px] font-bold font-mono tabular-nums text-slate-100">{decimalToAmerican(homeOdds)}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{homeOdds ? homeOdds.toFixed(2) : "—"}</p>
        </div>
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600">Draw</p>
          <p className="text-[15px] font-bold font-mono tabular-nums text-slate-100">{decimalToAmerican(drawOdds)}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{drawOdds ? drawOdds.toFixed(2) : "—"}</p>
        </div>
        <div className="rounded-lg bg-surface-1 border border-edge px-2 py-2">
          <p className="text-[9px] uppercase tracking-widest text-slate-600 truncate">{match.away.name}</p>
          <p className="text-[15px] font-bold font-mono tabular-nums text-slate-100">{decimalToAmerican(awayOdds)}</p>
          <p className="text-[10px] text-slate-500 font-mono tabular-nums">{awayOdds ? awayOdds.toFixed(2) : "—"}</p>
        </div>
      </div>

      {/* Hero number + verdict line. Hero is the model's calibrated probability
          for the pick, sized like a headline so it lands without scrolling. */}
      <div className="flex items-baseline gap-3 mb-2">
        <p className="text-[40px] sm:text-[44px] font-black tabular-nums leading-none text-slate-100">
          {Math.round(pick.modelProb * 100)}%
        </p>
        <p className="text-[14px] text-slate-300 leading-snug">
          {pick.side === "draw" ? "to draw" : `${pick.label} to win`}
        </p>
      </div>
      <p className="text-[15px] font-bold text-slate-100 leading-snug mb-3">
        {line}
      </p>

      {/* Supporting numbers — fair price, edge, suggested stake.
          Only shown when there's a meaningful pick (no point on Pass/Avoid). */}
      {(band === "strong" || band === "lean") && (
        <div className="grid grid-cols-3 gap-3 pt-3 border-t border-edge/40">
          <div>
            <p className="text-[9px] uppercase tracking-widest text-slate-600">Edge vs market</p>
            <p className={`text-[14px] font-bold font-mono tabular-nums ${s.edgeTone}`}>
              {pick.edgePts >= 0 ? "+" : ""}{pick.edgePts.toFixed(1)}<span className="text-[9px] font-normal opacity-70">pt</span>
            </p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-widest text-slate-600">Fair price</p>
            <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">
              {pick.fairOdds ? `$${pick.fairOdds.toFixed(2)}` : "—"}
            </p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-widest text-slate-600">Suggested stake</p>
            <p className="text-[14px] font-bold font-mono tabular-nums text-slate-100">
              {pick.kellyPct != null ? `${pick.kellyPct.toFixed(1)}u` : "—"}
              <span className="text-[9px] font-normal text-slate-500 ml-1">¼-Kelly</span>
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
