"use client"
/**
 * Live match hub page — scrollable feed of live WC matches.
 *
 * Two modes:
 *  - Fun (default): WP sparkline + possession + shots + xG
 *  - Gambling (toggle): fair odds + value picks + bet tracker
 *
 * SSE connection refreshes all card data every 15s.
 */
import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { MiniSparkline } from "@/components/match/MiniSparkline"
import { MarketsMini } from "@/components/live/MarketsMini"
import { BetSlip } from "@/components/live/BetSlip"

interface MatchCard {
  match_id: string
  group: string
  matchday: number
  home_name: string
  away_name: string
  home_flag: string | null
  away_flag: string | null
  kickoff: string | null
  state: {
    status: string
    elapsed_min: number
    home_score: number
    away_score: number
    home_possession: number | null
    away_possession: number | null
    home_shots: number | null
    away_shots: number | null
    home_shots_on_target: number | null
    away_shots_on_target: number | null
    home_xg: number | null
    away_xg: number | null
  }
  wp: { p_home: number; p_draw: number; p_away: number } | null
  sparkline: Array<{ e: number; h: number; a: number }>
}

interface HubData {
  live_count: number
  matches: MatchCard[]
}

export function LiveHub({ initialData }: { initialData: HubData | null }) {
  const [data, setData] = useState<HubData | null>(initialData)
  const [gamble, setGamble] = useState(false)
  const [betStake, setBetStake] = useState<number | null>(null)

  // Poll hub every 15s (SSE per-match is overkill for a card feed)
  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch("/api/live/hub")
        if (r.ok) setData(await r.json())
      } catch { /* keep stale data */ }
    }, 15000)
    return () => clearInterval(iv)
  }, [])

  if (!data || data.matches.length === 0) {
    return (
      <div className="max-w-2xl mx-auto px-3 sm:px-5 py-12 text-center">
        <p className="text-[16px] text-slate-400 font-semibold mb-2">No live matches right now</p>
        <p className="text-[12px] text-slate-600">
          This page lights up when World Cup fixtures are in play.
          <br />
          <Link href="/" className="text-emerald-400 hover:underline">Browse upcoming matches →</Link>
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-3 sm:px-5 py-4">
      {/* Mode toggle */}
      <div className="flex items-center justify-end gap-2 mb-3">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Fun</span>
        <button
          onClick={() => setGamble((v) => !v)}
          className={`relative w-10 h-5 rounded-full transition-colors ${gamble ? "bg-amber-500" : "bg-slate-700"}`}
          aria-label={`Switch to ${gamble ? "fun" : "gambling"} mode`}
        >
          <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${gamble ? "translate-x-5" : ""}`} />
        </button>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Bet</span>
      </div>

      {/* Match cards */}
      <div className="space-y-3">
        {data.matches.map((m) => (
          <LiveMatchCard key={m.match_id} match={m} gamble={gamble} betStake={betStake} setBetStake={setBetStake} />
        ))}
      </div>
    </div>
  )
}

function LiveMatchCard({
  match: m,
  gamble,
  betStake,
  setBetStake,
}: {
  match: MatchCard
  gamble: boolean
  betStake: number | null
  setBetStake: (n: number | null) => void
}) {
  const homePct = m.wp ? Math.round(m.wp.p_home * 100) : null
  const drawPct = m.wp ? Math.round(m.wp.p_draw * 100) : null
  const awayPct = m.wp ? Math.round(m.wp.p_away * 100) : null

  return (
    <Link
      href={`/match/${m.match_id}`}
      className="block rounded-2xl border border-edge bg-surface-2 shadow-e1 hover:border-emerald-500/30 transition-colors overflow-hidden"
    >
      {/* Header: teams + score */}
      <div className="px-4 pt-3.5 pb-3 flex items-center justify-between border-b border-edge/40">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-[14px] font-bold text-white">
            {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />}
            <span className="truncate">{m.home_name}</span>
          </div>
          <div className="flex items-center gap-2 text-[14px] font-bold text-white mt-1">
            {m.away_flag && <img src={m.away_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />}
            <span className="truncate">{m.away_name}</span>
          </div>
        </div>
        <div className="text-right shrink-0 ml-3">
          <p className="font-mono text-[28px] tabular-nums font-black text-white leading-none">
            {m.state.home_score}–{m.state.away_score}
          </p>
          <div className="flex items-center gap-1.5 justify-end mt-0.5">
            <span className="w-1.5 h-1.5 bg-rose-500 rounded-full animate-pulse" />
            <span className="text-[11px] text-slate-400 font-mono tabular-nums">{m.state.elapsed_min}&apos;</span>
          </div>
        </div>
      </div>

      {/* WP + sparkline */}
      {m.wp && m.sparkline.length > 1 && (
        <div className="px-4 py-3 flex items-center gap-3 border-b border-edge/30">
          <div className="grid grid-cols-3 gap-2 text-center flex-1">
            <div>
              <p className="text-[12px] font-mono tabular-nums font-bold text-emerald-400">{homePct}%</p>
              <p className="text-[9px] text-slate-500">Home</p>
            </div>
            <div>
              <p className="text-[12px] font-mono tabular-nums font-bold text-slate-400">{drawPct}%</p>
              <p className="text-[9px] text-slate-500">Draw</p>
            </div>
            <div>
              <p className="text-[12px] font-mono tabular-nums font-bold text-orange-400">{awayPct}%</p>
              <p className="text-[9px] text-slate-500">Away</p>
            </div>
          </div>
          <MiniSparkline data={m.sparkline} />
        </div>
      )}

      {/* Stats row (fun mode) */}
      {!gamble && m.state && (
        <div className="px-4 py-2.5 grid grid-cols-3 gap-2 text-[10px] font-mono tabular-nums">
          {m.state.home_possession != null && (
            <div>
              <p className="text-slate-600 mb-0.5">Possession</p>
              <p className="text-slate-200">{Math.round(m.state.home_possession)} / {Math.round(m.state.away_possession || 0)}</p>
            </div>
          )}
          {(m.state.home_shots != null || m.state.away_shots != null) && (
            <div>
              <p className="text-slate-600 mb-0.5">Shots (on target)</p>
              <p className="text-slate-200">{m.state.home_shots ?? 0}({m.state.home_shots_on_target ?? 0}) / {m.state.away_shots ?? 0}({m.state.away_shots_on_target ?? 0})</p>
            </div>
          )}
          {m.state.home_xg != null && m.state.away_xg != null && (
            <div>
              <p className="text-slate-600 mb-0.5">xG</p>
              <p className="text-slate-200">{m.state.home_xg.toFixed(2)} / {m.state.away_xg.toFixed(2)}</p>
            </div>
          )}
        </div>
      )}

      {/* Gambling mode row */}
      {gamble && (
        <div className="px-4 py-2.5" onClick={(e) => e.preventDefault()}>
          <BetSlip
            matchId={m.match_id}
            homeName={m.home_name}
            awayName={m.away_name}
            stake={betStake}
            setStake={setBetStake}
          />
        </div>
      )}

      {/* Footer with group tag */}
      <div className="px-4 py-2 border-t border-edge/40 flex items-center justify-between text-[9px] text-slate-600">
        <span className="uppercase tracking-wider">Group {m.group} · MD{m.matchday}</span>
        <span>Tap for full detail →</span>
      </div>
    </Link>
  )
}
