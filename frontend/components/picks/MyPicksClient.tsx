"use client"
import { useEffect, useMemo, useState } from "react"
import type { Match } from "@/lib/types"

const STORAGE_KEY = "wc26_my_picks_v1"

interface UserPick {
  id: string
  created_at: string  // ISO
  match_id: string
  market: string       // home_win|draw|away_win|over_2_5|under_2_5|btts|btts_no
  odds: number
  stake: number       // units (1 = one unit)
  settled: boolean
  won: boolean | null
}

const MARKETS: { value: string; label: string }[] = [
  { value: "home_win", label: "Home win" },
  { value: "draw",     label: "Draw" },
  { value: "away_win", label: "Away win" },
  { value: "over_2_5", label: "Over 2.5 goals" },
  { value: "under_2_5", label: "Under 2.5 goals" },
  { value: "btts",     label: "Both teams to score" },
  { value: "btts_no",  label: "BTTS: no" },
]

const SETTLE: Record<string, (h: number, a: number) => boolean> = {
  home_win: (h, a) => h > a,
  draw:     (h, a) => h === a,
  away_win: (h, a) => a > h,
  over_2_5: (h, a) => (h + a) >= 3,
  under_2_5: (h, a) => (h + a) <= 2,
  btts:     (h, a) => h > 0 && a > 0,
  btts_no:  (h, a) => !(h > 0 && a > 0),
}

function read(): UserPick[] {
  if (typeof window === "undefined") return []
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as UserPick[]
  } catch { return [] }
}

function write(picks: UserPick[]) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(picks))
}

export function MyPicksClient({ matches }: { matches: Match[] }) {
  const [picks, setPicks] = useState<UserPick[]>([])
  const [matchId, setMatchId] = useState<string>("")
  const [market, setMarket] = useState<string>("home_win")
  const [odds, setOdds] = useState<string>("")
  const [stake, setStake] = useState<string>("1")

  const matchById = useMemo(() => {
    const m = new Map<string, Match>()
    for (const x of matches) m.set(x.id, x)
    return m
  }, [matches])

  useEffect(() => {
    let current = read()
    // Auto-settle picks whose match is complete
    let mutated = false
    for (const p of current) {
      if (p.settled) continue
      const m = matchById.get(p.match_id)
      if (!m) continue
      const home = (m as any).home_score
      const away = (m as any).away_score
      if (typeof home !== "number" || typeof away !== "number") continue
      const fn = SETTLE[p.market]
      if (!fn) continue
      p.won = fn(home, away)
      p.settled = true
      mutated = true
    }
    if (mutated) write(current)
    setPicks([...current])
  }, [matchById])

  const addPick = () => {
    if (!matchId) return
    const oddsNum = parseFloat(odds)
    const stakeNum = parseFloat(stake)
    if (!oddsNum || oddsNum <= 1 || !stakeNum || stakeNum <= 0) return
    const next: UserPick = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      created_at: new Date().toISOString(),
      match_id: matchId,
      market,
      odds: oddsNum,
      stake: stakeNum,
      settled: false,
      won: null,
    }
    const updated = [next, ...picks]
    write(updated)
    setPicks(updated)
    setOdds("")
  }

  const removePick = (id: string) => {
    const updated = picks.filter((p) => p.id !== id)
    write(updated)
    setPicks(updated)
  }

  const clearAll = () => {
    if (!confirm("Clear all saved picks? This can't be undone.")) return
    write([])
    setPicks([])
  }

  const settled = picks.filter((p) => p.settled)
  const totalStaked = settled.reduce((s, p) => s + p.stake, 0)
  const pnl = settled.reduce((s, p) => s + (p.won ? p.stake * (p.odds - 1) : -p.stake), 0)
  const roi = totalStaked > 0 ? (pnl / totalStaked) * 100 : null
  const hitRate = settled.length > 0 ? (settled.filter((p) => p.won).length / settled.length) * 100 : null

  return (
    <div className="space-y-5">
      <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Your track record</p>
        {settled.length === 0 ? (
          <p className="text-[12px] text-slate-400 leading-snug">
            No picks settled yet. Add one below — we&apos;ll auto-grade it after the match completes.
          </p>
        ) : (
          <div className="grid grid-cols-4 gap-3 text-center">
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Settled</p>
              <p className="font-mono tabular-nums text-[18px] font-bold text-slate-100">{settled.length}</p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Hit rate</p>
              <p className="font-mono tabular-nums text-[18px] font-bold text-emerald-400">
                {hitRate != null ? `${hitRate.toFixed(1)}%` : "—"}
              </p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">P/L (units)</p>
              <p className={`font-mono tabular-nums text-[18px] font-bold ${pnl >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                {pnl >= 0 ? "+" : ""}{pnl.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">ROI</p>
              <p className={`font-mono tabular-nums text-[18px] font-bold ${(roi ?? 0) >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                {roi != null ? `${roi >= 0 ? "+" : ""}${roi.toFixed(1)}%` : "—"}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Add a pick */}
      <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 space-y-3">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Log a pick</p>
        <div className="grid sm:grid-cols-2 gap-2">
          <select
            value={matchId}
            onChange={(e) => setMatchId(e.target.value)}
            className="bg-surface-0 border border-edge rounded-md px-2.5 py-2 text-[13px] text-slate-100 min-h-[36px]"
          >
            <option value="">— pick a match —</option>
            {matches.map((m) => (
              <option key={m.id} value={m.id}>
                {m.home.name} vs {m.away.name} · MD{m.matchday}
              </option>
            ))}
          </select>
          <select
            value={market}
            onChange={(e) => setMarket(e.target.value)}
            className="bg-surface-0 border border-edge rounded-md px-2.5 py-2 text-[13px] text-slate-100 min-h-[36px]"
          >
            {MARKETS.map((m) => (
              <option key={m.value} value={m.value}>{m.label}</option>
            ))}
          </select>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-600 shrink-0">Odds</label>
          <input
            inputMode="decimal"
            value={odds}
            onChange={(e) => setOdds(e.target.value)}
            placeholder="e.g. 1.85"
            className="bg-surface-0 border border-edge rounded-md px-2.5 py-1.5 text-[13px] text-slate-100 font-mono text-center min-h-[34px] w-24"
          />
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-600 shrink-0">Stake</label>
          <input
            inputMode="decimal"
            value={stake}
            onChange={(e) => setStake(e.target.value)}
            placeholder="units"
            className="bg-surface-0 border border-edge rounded-md px-2.5 py-1.5 text-[13px] text-slate-100 font-mono text-center min-h-[34px] w-20"
          />
          <button
            onClick={addPick}
            disabled={!matchId || !odds || !stake}
            className="ml-auto px-4 py-2 rounded-lg text-[12px] font-bold bg-emerald-500 text-white hover:bg-emerald-400 disabled:opacity-40"
          >
            Save pick
          </button>
        </div>
      </div>

      {/* Picks list */}
      {picks.length > 0 && (
        <div>
          <div className="flex items-baseline justify-between mb-2">
            <p className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">
              All picks ({picks.length})
            </p>
            <button
              onClick={clearAll}
              className="text-[10px] text-slate-600 hover:text-amber-400 underline"
            >
              Clear all
            </button>
          </div>
          <ul className="space-y-2">
            {picks.map((p) => {
              const m = matchById.get(p.match_id)
              const label = m ? `${m.home.name} vs ${m.away.name}` : p.match_id
              const market = MARKETS.find((x) => x.value === p.market)?.label ?? p.market
              const pnl = p.settled ? (p.won ? p.stake * (p.odds - 1) : -p.stake) : null
              return (
                <li
                  key={p.id}
                  className={`rounded-lg border px-3 py-2.5 flex items-baseline justify-between gap-2 ${
                    !p.settled ? "border-edge bg-surface-2" :
                    p.won ? "border-emerald-700/40 bg-emerald-950/30" :
                    "border-amber-700/40 bg-amber-950/20"
                  }`}
                >
                  <div className="min-w-0">
                    <p className="text-[12px] text-slate-200 font-semibold truncate">{label}</p>
                    <p className="text-[11px] text-slate-500">
                      {market} @ <span className="font-mono text-slate-300">{p.odds.toFixed(2)}</span> · {p.stake}u
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    {p.settled ? (
                      <>
                        <p className={`text-[12px] font-mono font-bold ${p.won ? "text-emerald-400" : "text-amber-400"}`}>
                          {p.won ? "WON" : "LOST"}
                        </p>
                        <p className={`text-[10.5px] font-mono ${pnl != null && pnl >= 0 ? "text-emerald-300" : "text-amber-300"}`}>
                          {pnl != null && pnl >= 0 ? "+" : ""}{pnl?.toFixed(2)}u
                        </p>
                      </>
                    ) : (
                      <p className="text-[10px] text-slate-500 uppercase">pending</p>
                    )}
                    <button
                      onClick={() => removePick(p.id)}
                      className="text-[10px] text-slate-600 hover:text-amber-400 mt-1"
                      title="Remove"
                    >×</button>
                  </div>
                </li>
              )
            })}
          </ul>
        </div>
      )}

      <p className="text-[10px] text-slate-600 leading-snug px-1">
        Picks live in this browser only — clearing your data or switching device will wipe them. We do not store anything server-side.
        Stakes are units; P/L is in units. 18+ only.
      </p>
    </div>
  )
}
