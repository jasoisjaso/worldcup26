import type { MatchPrediction, Market } from "@/lib/types"

/**
 * Model vs Market — the single "informed decision" signal.
 *
 * For each main market it shows the model's probability next to the
 * bookmaker's implied probability (1 / decimal odds), and the EDGE between
 * them. A positive edge where the model > the book is where the value lives;
 * a large edge is also where you should be most sceptical (the market is
 * sharp, so big disagreements are usually model error, not free money). We
 * surface the reliability tier the backend already computes so the user can
 * tell those two cases apart at a glance.
 *
 * Suppressed entirely when odds_source is "estimated" (no real book line yet)
 * — there is nothing real to disagree with, and showing a divergence against
 * our own placeholder odds would be misleading.
 */

function impliedFromOdds(odds: number | null | undefined): number | null {
  if (!odds || odds <= 1) return null
  return 1 / odds // vigged implied prob — fine for a "where we disagree" read
}

const TIER_COPY: Record<string, { label: string; tone: string }> = {
  solid: { label: "believable", tone: "text-emerald-300" },
  speculative: { label: "be cautious", tone: "text-amber-300" },
  longshot: { label: "likely model noise", tone: "text-rose-300" },
}

function Row({ m }: { m: Market }) {
  const model = m.our_prob
  const implied = m.market_implied ?? impliedFromOdds(m.bookmaker_odds)
  if (implied == null) return null

  const edge = model - implied // >0: model rates it higher than the book
  const edgePct = edge * 100
  const modelPct = Math.round(model * 100)
  const impliedPct = Math.round(implied * 100)

  // Scale bars to the larger of the two so both are visible on one track.
  const denom = Math.max(model, implied, 0.01)
  const modelW = (model / denom) * 100
  const impliedW = (implied / denom) * 100

  const tier = m.reliability ? TIER_COPY[m.reliability] : null
  const edgeTone =
    Math.abs(edgePct) < 2 ? "text-slate-400"
    : edge > 0 ? "text-emerald-300"
    : "text-rose-300"

  return (
    <div className="py-3 first:pt-0 last:pb-0">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[12px] font-semibold text-slate-200">{m.label}</span>
        <span className={`text-[12px] font-mono tabular-nums font-bold ${edgeTone}`}>
          {edge > 0 ? "+" : ""}{edgePct.toFixed(1)}<span className="text-[10px] font-normal opacity-70">pt</span>
        </span>
      </div>

      {/* Model bar (emerald) over Market bar (slate) — same track, so the gap
          between them IS the edge, read visually. */}
      <div className="space-y-1">
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-[9px] uppercase tracking-wider text-emerald-400/80">Model</span>
          <div className="flex-1 h-2 rounded-full bg-surface-3 overflow-hidden">
            <div className="h-full rounded-full bg-emerald-500/80" style={{ width: `${modelW}%` }} />
          </div>
          <span className="w-9 shrink-0 text-[11px] font-mono tabular-nums text-slate-200 text-right">{modelPct}%</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="w-12 shrink-0 text-[9px] uppercase tracking-wider text-slate-500">Bookie</span>
          <div className="flex-1 h-2 rounded-full bg-surface-3 overflow-hidden">
            <div className="h-full rounded-full bg-slate-500/70" style={{ width: `${impliedW}%` }} />
          </div>
          <span className="w-9 shrink-0 text-[11px] font-mono tabular-nums text-slate-400 text-right">{impliedPct}%</span>
        </div>
      </div>

      {/* Verdict line: only when there's a meaningful edge AND a reliability read. */}
      {tier && edgePct >= 2 && (
        <p className="text-[10px] text-slate-500 mt-1.5">
          Model sees value here,{" "}
          <span className={tier.tone}>{tier.label}</span>
          {m.is_positive_ev && edge > 0 && (
            <span className="text-emerald-400/80"> · +EV at {m.bookmaker_odds.toFixed(2)}</span>
          )}
        </p>
      )}
      {edgePct <= -2 && (
        <p className="text-[10px] text-slate-500 mt-1.5">
          Bookie rates this higher than the model, so the market disagrees with us.
        </p>
      )}
    </div>
  )
}

export function ModelVsMarket({ p }: { p: MatchPrediction }) {
  // Nothing real to compare against when odds are our own placeholder.
  if (p.odds_source === "estimated" || !p.odds_source) return null

  const markets = (p.markets ?? []).filter(
    (m) => (m.market_implied ?? impliedFromOdds(m.bookmaker_odds)) != null,
  )
  if (markets.length === 0) return null

  const sourceLabel =
    p.odds_source === "sharp+live" || p.odds_source === "sharp"
      ? "sharp (Pinnacle) line"
      : "bookmaker line"

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5">
      <div className="flex items-baseline justify-between mb-1">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Model vs market</p>
        <p className="text-[10px] text-slate-600 font-mono">{sourceLabel}</p>
      </div>
      <p className="text-[11px] text-slate-500 leading-snug mb-3">
        Where our model disagrees with the odds. A green edge is where the model sees value, but a
        sharp market is hard to beat, so trust the small, believable gaps over the big ones.
      </p>
      <div className="divide-y divide-edge/40">
        {markets.map((m) => (
          <Row key={m.market} m={m} />
        ))}
      </div>
    </div>
  )
}
