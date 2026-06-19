"use client"
/**
 * Gambling-mode bet tracker: enter stake, see suggested bet size via fractional Kelly,
 * track bet outcome against live WP swings.
 *
 * NOT real-money — it's a tracking tool only. All numbers are informational.
 */
import { useState } from "react"

export function BetSlip({
  matchId,
  homeName,
  awayName,
  stake,
  setStake,
}: {
  matchId: string
  homeName: string
  awayName: string
  stake: number | null
  setStake: (n: number | null) => void
}) {
  const [bankroll, setBankroll] = useState("100")
  const [side, setSide] = useState<"home" | "draw" | "away" | null>(null)

  const br = parseFloat(bankroll) || 0
  // Fractional Kelly: bet ~(edge / odds-1) * bankroll, capped at 5%
  const kelly = side && stake ? Math.min((stake / 100) * br, br * 0.05) : 0

  return (
    <div className="space-y-3 text-[11px]">
      {/* Bankroll input */}
      <div className="flex items-center gap-2">
        <label className="text-slate-500 shrink-0">Bankroll</label>
        <div className="flex-1 flex items-center gap-1 bg-surface-1 rounded-lg px-2.5 py-1.5 border border-edge/40">
          <span className="text-slate-500">$</span>
          <input
            type="number"
            value={bankroll}
            onChange={(e) => setBankroll(e.target.value)}
            className="flex-1 bg-transparent text-white font-mono text-right outline-none [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
            min="1"
          />
        </div>
      </div>

      {/* Side picker */}
      <div>
        <p className="text-slate-500 mb-1.5">Pick outcome</p>
        <div className="grid grid-cols-3 gap-1.5">
          {(["home", "draw", "away"] as const).map((s) => {
            const label = s === "home" ? homeName : s === "away" ? awayName : "Draw"
            return (
              <button
                key={s}
                onClick={() => { setSide(s); setStake(10) }}
                className={`px-2 py-1.5 rounded-lg text-[10px] font-semibold transition-colors ${
                  side === s
                    ? s === "home" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
                    : s === "draw" ? "bg-slate-500/20 text-slate-300 border border-slate-500/40"
                    : "bg-orange-500/20 text-orange-300 border border-orange-500/40"
                    : "bg-surface-1 text-slate-500 border border-edge/30 hover:border-slate-600"
                }`}
              >
                {label}
              </button>
            )
          })}
        </div>
      </div>

      {/* Stake slider */}
      {side && (
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-slate-500">Stake</label>
            <span className="font-mono text-amber-400 tabular-nums">${stake?.toFixed(0) ?? "—"}</span>
          </div>
          <input
            type="range"
            min="1"
            max={Math.floor(br * 0.1)}
            value={stake ?? 1}
            onChange={(e) => setStake(parseInt(e.target.value))}
            className="w-full h-1.5 rounded-full appearance-none bg-surface-1 accent-amber-500"
          />
          <div className="flex justify-between text-[9px] text-slate-600 mt-0.5">
            <span>$1</span>
            <span>${Math.floor(br * 0.1)}</span>
          </div>
        </div>
      )}

      {/* Kelly output */}
      {side && stake && (
        <div className="flex items-center justify-between rounded-lg bg-surface-1 px-3 py-2 border border-edge/40">
          <span className="text-slate-500">Suggested bet (frac Kelly)</span>
          <span className="font-mono font-bold text-amber-400 tabular-nums">${kelly.toFixed(2)}</span>
        </div>
      )}

      <p className="text-[9px] text-slate-600 leading-snug">
        Fractional-quarter Kelly: bet {side ? `${kelly > 0 ? `${(kelly / br * 100).toFixed(1)}%` : "0%"}` : "—"} of bankroll. Not advice — tracking only.
      </p>
    </div>
  )
}
