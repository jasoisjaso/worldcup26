"use client"
import { useEffect, useState } from "react"
import type { ValueOpportunity } from "@/lib/types"

function reliabilityChip(reliability?: string): { label: string; cls: string } {
  // Trust is how far the model strays from a sharp market, NOT raw EV (which rewards
  // longshots where the model is most likely just wrong).
  if (reliability === "solid") return { label: "Solid edge", cls: "bg-emerald-500/15 text-emerald-300 border-emerald-500/40" }
  if (reliability === "speculative") return { label: "Speculative", cls: "bg-amber-500/15 text-amber-300 border-amber-500/40" }
  return { label: "Longshot", cls: "bg-slate-500/15 text-slate-400 border-slate-500/40" }
}

/** Model chance vs the bookie's implied chance on a shared 0-100% scale; the gap is the edge. */
function EdgeBar({ modelPct, marketPct }: { modelPct: number; marketPct: number }) {
  const lo = Math.min(modelPct, marketPct)
  const hi = Math.max(modelPct, marketPct)
  const gainsToModel = modelPct >= marketPct
  return (
    <div>
      <div className="relative h-6 rounded-lg bg-surface-1 overflow-hidden">
        <div
          className={`absolute inset-y-0 ${gainsToModel ? "bg-emerald-500/30" : "bg-amber-500/30"}`}
          style={{ left: `${lo}%`, width: `${hi - lo}%` }}
        />
        <div className="absolute inset-y-0 w-[2px] bg-slate-400" style={{ left: `${marketPct}%` }} />
        <div className="absolute inset-y-0 w-[2px] bg-emerald-400" style={{ left: `${modelPct}%` }} />
      </div>
      <div className="flex justify-between mt-1 text-[10.5px]">
        <span className="text-slate-500">Bookie <span className="font-mono tabular-nums text-slate-300">{marketPct}%</span></span>
        <span className="text-slate-500">Model <span className="font-mono tabular-nums text-emerald-400 font-bold">{modelPct}%</span></span>
      </div>
    </div>
  )
}

function money(n: number): string {
  return n >= 1000 ? `$${(n / 1000).toFixed(n >= 10000 ? 0 : 1)}k` : `$${Math.round(n)}`
}

// Quarter-Kelly fraction, capped at 5% of bankroll (matches the backend single-bet sizing).
function quarterKelly(prob: number, odds: number): number {
  const b = odds - 1
  if (b <= 0) return 0
  const f = (b * prob - (1 - prob)) / b
  return Math.max(0, Math.min(f * 0.25, 0.05))
}

type TierRec = { n: number; correct: number; rate: number }

function tierName(reliability?: string): string {
  if (reliability === "solid") return "Solid-edge"
  if (reliability === "speculative") return "Speculative"
  return "Longshot"
}

function OpportunityCard({
  opp, bankroll, tierRecord,
}: { opp: ValueOpportunity; bankroll: number | null; tierRecord?: Record<string, TierRec> }) {
  const marketPct = Math.round((1 / opp.bookmaker_odds) * 100)
  const modelPct = Math.round((opp.model_prob ?? opp.our_prob) * 100)
  const gap = modelPct - marketPct
  const chip = reliabilityChip(opp.reliability)
  const isLongshot = opp.reliability === "longshot"
  const evPct = (opp.ev_best ?? opp.ev) * 100
  const bestPrice = opp.best_price ?? opp.bookmaker_odds

  // Focal-number heat: brighter emerald the larger the edge (auto-sorted, so card 1 is hottest).
  const evClass = evPct >= 8 ? "text-emerald-300" : evPct >= 4 ? "text-emerald-400" : "text-emerald-500"

  // Calibration-shrunk staking: size on the LOWER of what the model claims and what picks
  // at this reliability tier have actually delivered. Never stakes more than raw Kelly, so
  // it cannot raise ruin risk; it cuts the stake exactly when the model has been overconfident.
  const tierRec = tierRecord?.[opp.reliability ?? "longshot"]
  const shrunk = tierRec != null && tierRec.n >= 4 && tierRec.rate < modelPct / 100
  const stakeProb = shrunk ? tierRec!.rate : modelPct / 100
  const stakePct = Math.round(quarterKelly(stakeProb, bestPrice) * 100 * 10) / 10
  const stakeDollars = bankroll != null && stakePct > 0 ? bankroll * (stakePct / 100) : null

  return (
    <div className="bg-surface-2 border border-edge rounded-card shadow-e1 p-4 hover:border-edge-strong transition-colors">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[10px] text-slate-600 font-bold uppercase tracking-widest mb-1">
            MD{opp.matchday} · {opp.match_label}
          </p>
          <p className="text-[16px] font-bold text-white leading-tight">{opp.label}</p>
        </div>
        <span className={`shrink-0 text-[9.5px] font-bold uppercase tracking-wide px-2 py-1 rounded-md border ${chip.cls}`}>
          {chip.label}
        </span>
      </div>

      {/* Focal number: the one figure that says how good this bet is. */}
      <div className="mt-3 flex items-end gap-3">
        <div>
          <p className={`font-mono tabular-nums text-[38px] font-extrabold leading-none ${evClass}`}>
            +{evPct.toFixed(1)}<span className="text-[22px]">%</span>
          </p>
          <p className="text-[10px] uppercase tracking-wider text-slate-500 mt-1">expected value</p>
        </div>
        <p className="text-[12px] text-slate-400 leading-snug pb-1">
          ≈ <span className="text-slate-200 font-semibold">{money(evPct)}</span> profit per $100<br />staked, over the long run
        </p>
      </div>

      <div className="mt-3">
        <EdgeBar modelPct={modelPct} marketPct={marketPct} />
        <p className="text-[10.5px] text-slate-500 mt-1.5">
          Model rates this <span className={gap >= 0 ? "text-emerald-400 font-semibold" : "text-amber-500 font-semibold"}>{gap >= 0 ? "+" : ""}{gap} pts</span> vs the bookie&apos;s price.
        </p>
      </div>

      <div className="flex items-center justify-between gap-2 mt-3 rounded-lg bg-emerald-950/25 border border-emerald-800/40 px-3 py-2">
        <span className="text-[11px] text-slate-300">
          <span aria-hidden="true" className="text-emerald-400">↑ </span>Best price
          <span className="font-mono font-bold text-emerald-400"> {bestPrice.toFixed(2)}</span>
          {opp.best_book && <span className="text-white font-semibold"> @ {opp.best_book}</span>}
        </span>
        {stakePct > 0 && (
          <span className="text-[11px] text-slate-400 whitespace-nowrap">
            Stake{" "}
            <span className="font-mono font-bold text-slate-200">
              {stakeDollars != null ? money(stakeDollars) : `${stakePct.toFixed(1)}%`}
            </span>
            <span className="text-slate-600"> (¼-Kelly)</span>
          </span>
        )}
      </div>

      {shrunk && (
        <p className="text-[10px] text-slate-500 mt-1.5">
          Stake sized on the proven <span className="text-slate-300 font-semibold">{Math.round(tierRec!.rate * 100)}%</span> hit
          rate at this confidence, not the model&apos;s {modelPct}%, so we never overbet an edge the record has not earned.
        </p>
      )}

      {(() => {
        // The differentiator: our own public track record at this exact reliability, shown
        // right at the decision. Only once the bucket has enough settled picks to mean something.
        const rec = tierRecord?.[opp.reliability ?? "longshot"]
        if (!rec || rec.n < 4) return null
        const pct = Math.round(rec.rate * 100)
        return (
          <p className="text-[10.5px] text-slate-400 mt-3 rounded-lg bg-surface-1 border border-edge px-3 py-2">
            <span className="text-slate-500">Track record: </span>
            {tierName(opp.reliability)} picks have hit{" "}
            <span className="font-mono tabular-nums text-emerald-400 font-semibold">{rec.correct} of {rec.n}</span>{" "}
            ({pct}%) so far, logged before kickoff and graded in public.
          </p>
        )
      })()}

      {isLongshot && (
        <p className="text-[10.5px] text-amber-400/90 leading-snug mt-3">
          <span aria-hidden="true">⚠ </span>High risk: the model rates this well above the bookie, but a sharp market rarely
          misprices by this much. Treat it as a long shot.
        </p>
      )}
    </div>
  )
}

export function ValueList({ opps, tierRecord }: { opps: ValueOpportunity[]; tierRecord?: Record<string, TierRec> }) {
  const [bankroll, setBankroll] = useState<number | null>(null)
  const [raw, setRaw] = useState("")

  useEffect(() => {
    const saved = localStorage.getItem("wc26_bankroll")
    if (saved) {
      setRaw(saved)
      const n = parseFloat(saved)
      if (!isNaN(n) && n > 0) setBankroll(n)
    }
  }, [])

  function onChange(v: string) {
    setRaw(v)
    const n = parseFloat(v.replace(/[^0-9.]/g, ""))
    if (!isNaN(n) && n > 0) {
      setBankroll(n)
      localStorage.setItem("wc26_bankroll", String(n))
    } else {
      setBankroll(null)
      localStorage.removeItem("wc26_bankroll")
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3 rounded-lg bg-surface-2 border border-edge px-3 py-2">
        <label htmlFor="bankroll" className="text-[11px] text-slate-400 font-semibold whitespace-nowrap">
          Your bankroll
        </label>
        <div className="relative flex-1 max-w-[160px]">
          <span className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[12px] text-slate-500">$</span>
          <input
            id="bankroll"
            inputMode="decimal"
            value={raw}
            onChange={(e) => onChange(e.target.value)}
            placeholder="1,000"
            className="w-full bg-surface-1 border border-edge rounded-md pl-5 pr-2 py-1.5 text-[13px] text-slate-100 font-mono tabular-nums focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
        <span className="text-[10.5px] text-slate-600 leading-snug">
          {bankroll != null ? "Stakes shown in dollars (¼-Kelly)" : "Set it to see each stake in dollars"}
        </span>
      </div>

      <div className="space-y-3">
        {opps.map((opp, i) => (
          <OpportunityCard key={`${opp.match_id}-${opp.market}-${i}`} opp={opp} bankroll={bankroll} tierRecord={tierRecord} />
        ))}
      </div>
    </div>
  )
}
