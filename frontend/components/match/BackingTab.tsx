import type { MatchPrediction, Match, BackingPick } from "@/lib/types"

/**
 * Backing X tab. Shown when a user has signalled they're backing one
 * side ("Backing Brazil", "Backing Scotland"). Replaces the regular
 * verdict block with a three-card pattern that acknowledges the bet
 * is happening and gives the smartest way to execute it.
 *
 * Voice rules (validated v2 in the paper test):
 *
 * 1. State the math, the reader decides.
 * 2. Numbers do the talking, no editorial filler.
 * 3. No moralising. Stake sizes flat, dry.
 * 4. Task-focused phrasing, no demands.
 *
 * Cards always in this order:
 *   1. Straight back on 1X2 (honest "no edge" / "edge" / "small edge").
 *   2. Smarter bet (highest-edge alt market on this side).
 *   3. Cleaner alternative (second-best alt market on this side).
 */

type Side = "home" | "away"

function quarterKelly(modelProb: number, bookOdds: number, bankroll = 1000): number | null {
  if (bookOdds <= 1 || modelProb <= 0) return null
  const b = bookOdds - 1
  const q = 1 - modelProb
  const full = (modelProb * b - q) / b
  if (full <= 0) return null
  const fraction = full / 4
  return Math.min(fraction, 0.05) * bankroll
}

function pickedTeam(prediction: MatchPrediction, side: Side, match: Match): {
  name: string
  modelProb: number
  marketImplied: number | null
  bookOdds: number | null
} {
  const market = side === "home" ? "home_win" : "away_win"
  const mk = (prediction.markets ?? []).find((x) => x.market === market)
  return {
    name: side === "home" ? match.home.name : match.away.name,
    modelProb: side === "home" ? prediction.home_win : prediction.away_win,
    marketImplied: mk?.market_implied ?? null,
    bookOdds: mk?.bookmaker_odds ?? null,
  }
}

function StraightCard({
  side, prediction, match,
}: { side: Side; prediction: MatchPrediction; match: Match }) {
  const t = pickedTeam(prediction, side, match)
  const modelPct = Math.round(t.modelProb * 100)
  const impliedPct = t.marketImplied != null ? Math.round(t.marketImplied * 100) : null
  const edgePts = (t.marketImplied != null) ? (t.modelProb - t.marketImplied) * 100 : 0
  const stake = (t.bookOdds && t.modelProb > 0) ? quarterKelly(t.modelProb, t.bookOdds, 1000) : null

  let badge: string
  let body: string
  if (impliedPct == null) {
    badge = "No live price"
    body = `No book line yet on a straight ${t.name} win.`
  } else if (edgePts >= 5 && t.modelProb / t.marketImplied! >= 1.08) {
    badge = "Edge"
    body = `Model has ${t.name} at ${modelPct}%. Bookies imply ${impliedPct}%. ${Math.abs(edgePts).toFixed(0)}-point gap.`
  } else if (edgePts >= 2 && t.modelProb / t.marketImplied! >= 1.04) {
    badge = "Small edge"
    body = `Model has ${t.name} at ${modelPct}%. Bookies imply ${impliedPct}%. ${Math.abs(edgePts).toFixed(0)}-point gap.`
  } else {
    badge = "No edge"
    body = `Model has ${t.name} at ${modelPct}%. Bookies imply ${impliedPct}%. Inside the noise band.`
  }

  return (
    <Card badge={badge} title={`Straight ${t.name} win`} body={body}>
      {(badge === "Edge" || badge === "Small edge") && stake != null && t.bookOdds && (
        <StakeLine stakeDollar={stake} bookOdds={t.bookOdds} />
      )}
    </Card>
  )
}

function AltCard({
  pick, label,
}: { pick: BackingPick; label: string }) {
  const modelPct = Math.round(pick.model_prob * 100)
  const impliedPct = Math.round(pick.market_implied * 100)
  const edge = Math.abs(pick.edge_pts)
  const positive = pick.edge_pts >= 2
  const badge = positive ? (pick.edge_pts >= 5 ? "Edge" : "Small edge") : "No edge"
  const body = positive
    ? `Model has ${pick.label} at ${modelPct}%. Bookies imply ${impliedPct}%. ${edge.toFixed(0)}-point gap.`
    : `Model has ${pick.label} at ${modelPct}%. Bookies imply ${impliedPct}%. No clear edge.`
  const stake = positive ? quarterKelly(pick.model_prob, pick.bookmaker_odds, 1000) : null

  return (
    <Card badge={badge} title={label} body={body}>
      {positive && stake != null && (
        <StakeLine stakeDollar={stake} bookOdds={pick.bookmaker_odds} />
      )}
    </Card>
  )
}

function Card({
  badge, title, body, children,
}: { badge: string; title: string; body: string; children?: React.ReactNode }) {
  const tone = badge === "Edge"
    ? "ring-emerald-500/40 border-emerald-700/40 bg-emerald-950/30"
    : badge === "Small edge"
      ? "ring-emerald-700/20 border-emerald-900/40 bg-emerald-950/15"
      : "ring-slate-700/30 border-edge bg-surface-2"
  const badgeTone = badge === "Edge"
    ? "bg-emerald-500/20 text-emerald-300"
    : badge === "Small edge"
      ? "bg-emerald-700/20 text-emerald-300"
      : "bg-slate-700/30 text-slate-300"

  return (
    <div className={`rounded-2xl border shadow-e1 p-4 ring-1 ${tone}`}>
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <span className={`text-[10px] font-bold uppercase tracking-[0.18em] px-2 py-0.5 rounded ${badgeTone}`}>
          {badge}
        </span>
      </div>
      {/* Match the verdict-block hero scale so all "decision" cards on the page
          share one disciplined size, regardless of which view the user is in. */}
      <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 leading-tight mb-2">{title}</p>
      <p className="text-[13px] text-slate-300 leading-relaxed mb-2">{body}</p>
      {children}
    </div>
  )
}

function StakeLine({ stakeDollar, bookOdds }: { stakeDollar: number; bookOdds: number }) {
  return (
    <div className="pt-2 border-t border-edge/40 mt-2">
      <p className="text-[12px] text-slate-200 leading-relaxed">
        <span className="font-bold font-mono tabular-nums text-slate-100">{(stakeDollar / 10).toFixed(1)}%</span>
        {" "}of bankroll{" "}
        <span className="text-slate-500">(${stakeDollar.toFixed(0)} on $1,000).</span>
        {" "}Take at{" "}
        <span className="font-bold font-mono tabular-nums text-slate-100">${bookOdds.toFixed(2)}</span>
        {" "}or longer.
      </p>
    </div>
  )
}

export function BackingTab({
  prediction, match, side,
}: { prediction: MatchPrediction; match: Match; side: Side }) {
  const story = prediction.team_story?.[side]
  const picks = prediction.backing_picks?.[side] ?? []
  const top2 = picks.slice(0, 2)
  const teamName = side === "home" ? match.home.name : match.away.name

  return (
    <div className="mb-5">
      {/* Header row identifies which side they're backing + an exit link */}
      <div className="rounded-2xl border border-edge bg-surface-2 px-4 py-3 mb-3 flex items-baseline justify-between gap-2">
        <p className="text-[12px] text-slate-300">
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400 mr-2">Backing</span>
          <span className="font-bold text-slate-100">{teamName}</span>
        </p>
        <a
          href={`?`}
          className="text-[10px] text-slate-500 hover:text-slate-300"
        >
          Clear
        </a>
      </div>

      {/* Team-story framing line above the cards */}
      {story && (
        <p className="text-[12px] text-slate-400 leading-relaxed mb-3 px-1">{story}</p>
      )}

      {/* Three cards: straight back, smarter bet, cleaner alternative.
          If picks.length < 2 we fall through gracefully (the 1X2 straight
          back card always renders; alts can be empty on placeholder data). */}
      <div className="space-y-3">
        <StraightCard side={side} prediction={prediction} match={match} />
        {top2[0] && <AltCard pick={top2[0]} label="The smarter bet" />}
        {top2[1] && <AltCard pick={top2[1]} label="Cleaner alternative" />}
      </div>
    </div>
  )
}
