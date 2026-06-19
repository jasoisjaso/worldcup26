"use client"
/**
 * Smart bet slip — real fair odds from our model vs market.
 *
 * Shows: outcome picker with our odds + market odds + edge %, fractional Kelly
 * suggestion based on actual bankroll input. Edge computed live.
 */
import { useState, useMemo } from "react"

interface FairOdds { home: number | null; draw: number | null; away: number | null }
interface Probs { home: number; draw: number; away: number }

export function SmartBetSlip({
  matchId, homeName, awayName, fairOdds, ourProbs, edge,
}: {
  matchId: string; homeName: string; awayName: string
  fairOdds: FairOdds
  ourProbs: Probs | null
  edge: { home: number; draw: number; away: number } | null
}) {
  const [bankroll, setBankroll] = useState("100")
  const [side, setSide] = useState<"home" | "draw" | "away" | null>(null)
  const [kellyFraction, setKellyFraction] = useState(0.25)

  const br = parseFloat(bankroll) || 0

  const info = useMemo(() => {
    if (!side || !ourProbs) return null
    const ourP = ourProbs[side]
    const marketOdds = fairOdds[side]
    const marketP = marketOdds ? 1 / marketOdds : null
    const edgePct = edge ? edge[side] : 0
    // Kelly: f* = (p * odds - 1) / (odds - 1)
    const odds = marketOdds ?? 2.0
    const kellyFull = (ourP * odds - 1) / (odds - 1)
    const kellyFrac = Math.max(0, kellyFull * kellyFraction)
    const suggestedStake = kellyFrac * br
    return {
      ourProb: Math.round(ourP * 100),
      marketProb: marketP ? Math.round(marketP * 100) : null,
      edgePct,
      kellyFrac: Math.round(kellyFrac * 1000) / 10,
      suggestedStake: Math.round(suggestedStake * 100) / 100,
      odds,
    }
  }, [side, ourProbs, fairOdds, edge, br, kellyFraction])

  return (
    <div className="space-y-3 text-[11px]">
      {/* Bankroll */}
      <div className="flex items-center gap-2">
        <label className="text-slate-500 shrink-0">Bankroll</label>
        <div className="flex-1 flex items-center gap-1 bg-surface-1 rounded-lg px-2.5 py-1.5 border border-edge/40">
          <span className="text-slate-500">$</span>
          <input type="number" value={bankroll} onChange={(e) => setBankroll(e.target.value)}
            className="flex-1 bg-transparent text-white font-mono text-right outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none" min="1" />
        </div>
      </div>

      {/* Outcome picker */}
      <div>
        <p className="text-slate-500 mb-1.5">Pick outcome</p>
        <div className="grid grid-cols-3 gap-1.5">
          {(["home", "draw", "away"] as const).map((s) => {
            const label = s === "home" ? homeName : s === "away" ? awayName : "Draw"
            const odds = fairOdds[s]
            const e = edge?.[s] ?? 0
            return (
              <button key={s} onClick={() => setSide(s)}
                className={`px-2 py-2 rounded-lg text-[10px] font-semibold transition-colors ${
                  side === s
                    ? s === "home" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : s === "draw" ? "bg-slate-500/20 text-slate-300 border border-slate-500/40"
                    : "bg-orange-500/20 text-orange-300 border border-orange-500/40"
                    : "bg-surface-1 text-slate-500 border border-edge/30 hover:border-slate-600"
                }`}>
                <div>{label}</div>
                {odds && <div className="text-[9px] font-mono mt-0.5 opacity-70">{odds.toFixed(1)}</div>}
                {e !== 0 && <div className={`text-[9px] font-mono ${e > 0 ? "text-emerald-400" : "text-rose-400"}`}>{e > 0 ? "+" : ""}{e}% edge</div>}
              </button>
            )
          })}
        </div>
      </div>

      {/* Kelly fraction slider */}
      {side && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-slate-500">Kelly</label>
            <span className="font-mono text-amber-400 tabular-nums">{Math.round(kellyFraction * 100)}%</span>
          </div>
          <input type="range" min="0.05" max="1" step="0.05" value={kellyFraction}
            onChange={(e) => setKellyFraction(parseFloat(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none bg-surface-1 accent-amber-500" />
          <div className="flex justify-between text-[9px] text-slate-600 mt-0.5"><span>5% (safe)</span><span>100% (full)</span></div>
        </div>
      )}

      {/* Output */}
      {info && (
        <div className="rounded-lg bg-surface-1 p-3 border border-edge/40 space-y-1.5">
          <div className="flex justify-between">
            <span className="text-slate-500">Our probability</span>
            <span className="font-mono text-white tabular-nums">{info.ourProb}%</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Market odds</span>
            <span className="font-mono text-slate-200 tabular-nums">{info.odds.toFixed(1)}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Edge</span>
            <span className={`font-mono tabular-nums ${info.edgePct > 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {info.edgePct > 0 ? "+" : ""}{info.edgePct}%
            </span>
          </div>
          <div className="flex justify-between pt-1 border-t border-edge/30">
            <span className="text-slate-500">Fractional Kelly stake</span>
            <span className="font-mono font-bold text-amber-400 tabular-nums">${info.suggestedStake.toFixed(2)}</span>
          </div>
          <p className="text-[9px] text-slate-600">{info.kellyFrac}% of bankroll · tracking only, not advice</p>
        </div>
      )}
    </div>
  )
}
