"use client"
/**
 * Live match hub page — scrollable feed of live WC matches + coming up + just finished +
 * Golden Boot mini-leader. Two modes: Fun (default, stats only) and Bet (markets + tracker).
 *
 * Polls /api/live/hub every 15s. Upcoming/completed/topscores are server-loaded once then
 * client-refreshed on navigation return.
 */
import { useEffect, useState } from "react"
import Link from "next/link"
import { MiniSparkline } from "@/components/match/MiniSparkline"
import { BetSlip } from "@/components/live/BetSlip"

/* ---- types ---- */

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
    status: string; elapsed_min: number; home_score: number; away_score: number
    home_possession: number | null; away_possession: number | null
    home_shots: number | null; away_shots: number | null
    home_shots_on_target: number | null; away_shots_on_target: number | null
    home_xg: number | null; away_xg: number | null
  }
  wp: { p_home: number; p_draw: number; p_away: number } | null
  sparkline: Array<{ e: number; h: number; a: number }>
}

interface HubData { live_count: number; matches: MatchCard[] }

interface UpcomingMatch {
  id: string; home_name: string; away_name: string
  home_flag: string | null; away_flag: string | null
  kickoff: string | null; group: string; matchday: number
}

interface RecentMatch {
  id: string; home_name: string; away_name: string
  home_flag: string | null; away_flag: string | null
  home_score: number; away_score: number; group: string; matchday: number
}

interface ScorerRow {
  name: string; nationality?: string; photo?: string; goals: number; assists: number
  team_name?: string
}

interface TopscoresData {
  leaderboard: ScorerRow[]
}

/* ---- helpers ---- */

function localKickoff(iso: string | null): string {
  if (!iso) return ""
  try {
    return new Date(iso).toLocaleTimeString("en-AU", { hour: "2-digit", minute: "2-digit" })
  } catch { return "" }
}

/* ---- main ---- */

export function LiveHub({
  initialData, upcoming, completed, topscores,
}: {
  initialData: HubData | null
  upcoming: { matches: UpcomingMatch[] } | null
  completed: { matches: RecentMatch[] } | null
  topscores: TopscoresData | null
}) {
  const [data, setData] = useState<HubData | null>(initialData)
  const [gamble, setGamble] = useState(false)
  const [betStake, setBetStake] = useState<number | null>(null)

  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch("/api/live/hub")
        if (r.ok) setData(await r.json())
      } catch { /* keep stale */ }
    }, 15000)
    return () => clearInterval(iv)
  }, [])

  const noLive = !data || data.matches.length === 0
  const top = topscores?.leaderboard?.slice(0, 6) ?? []

  return (
    <div className="max-w-2xl mx-auto px-3 sm:px-5 py-4 space-y-4">

      {/* Mode toggle */}
      <div className="flex items-center justify-end gap-2">
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Fun</span>
        <button
          onClick={() => setGamble((v) => !v)}
          className={`relative w-10 h-5 rounded-full transition-colors ${gamble ? "bg-amber-500" : "bg-slate-700"}`}
          aria-label={`Switch to ${gamble ? "fun" : "betting"} mode`}
        >
          <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${gamble ? "translate-x-5" : ""}`} />
        </button>
        <span className="text-[10px] text-slate-500 uppercase tracking-wider">Bet</span>
      </div>

      {/* ---- LIVE MATCHES ---- */}
      {!noLive ? (
        <div className="space-y-3">
          {data.matches.map((m) => (
            <LiveMatchCard key={m.match_id} match={m} gamble={gamble} betStake={betStake} setBetStake={setBetStake} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-edge bg-surface-2 p-8 text-center">
          <p className="text-[16px] text-slate-400 font-semibold mb-1.5">No live matches right now</p>
          <p className="text-[12px] text-slate-600">
            This page lights up when World Cup fixtures are in play.
            <br />
            <Link href="/" className="text-emerald-400 hover:underline">Browse upcoming matches →</Link>
          </p>
        </div>
      )}

      {/* ---- COMING UP ---- */}
      {upcoming && upcoming.matches.length > 0 && (
        <div className="rounded-2xl border border-edge bg-surface-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-edge/40 flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Coming up</span>
            <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
          </div>
          <div className="divide-y divide-edge/30">
            {upcoming.matches.map((m) => (
              <Link key={m.id} href={`/match/${m.id}`}
                className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface-1 transition-colors">
                {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
                <span className="text-[12px] text-slate-200 font-medium truncate flex-1">
                  {m.home_name} v {m.away_name}
                </span>
                <span className="text-[11px] font-mono text-slate-500 tabular-nums shrink-0">
                  {localKickoff(m.kickoff)}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ---- JUST FINISHED ---- */}
      {completed && completed.matches.length > 0 && (
        <div className="rounded-2xl border border-edge bg-surface-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-edge/40 flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Just finished</span>
          </div>
          <div className="divide-y divide-edge/30">
            {completed.matches.map((m) => (
              <Link key={m.id} href={`/match/${m.id}`}
                className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface-1 transition-colors">
                {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
                <span className="text-[12px] text-slate-200 font-medium truncate flex-1">
                  {m.home_name} v {m.away_name}
                </span>
                <span className="text-[12px] font-mono font-bold text-white tabular-nums shrink-0">
                  {m.home_score}–{m.away_score}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* ---- GOLDEN BOOT MINI ---- */}
      {top.length > 0 && (
        <div className="rounded-2xl border border-amber-500/20 bg-gradient-to-br from-amber-500/[0.05] to-surface-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-amber-500/10 flex items-center justify-between">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-amber-400">⚽︎ Golden Boot</p>
            <Link href="/winner" className="text-[10px] text-amber-500 hover:text-amber-300">Full leaderboard →</Link>
          </div>
          <div className="divide-y divide-edge/20">
            {top.map((p, i) => (
              <div key={i} className="flex items-center gap-2.5 px-4 py-2">
                <span className="font-mono text-[10px] text-slate-600 w-3 text-center">{i + 1}</span>
                {p.photo ? (
                  <img src={p.photo} alt="" className="w-6 h-6 rounded-full ring-1 ring-white/10 object-cover shrink-0" />
                ) : <span className="w-6 h-6 rounded-full bg-surface-1 shrink-0" />}
                <div className="flex-1 min-w-0">
                  <p className="text-[11px] font-semibold text-slate-100 truncate">{p.name}</p>
                  <p className="text-[10px] text-slate-500 truncate">{p.nationality}{p.team_name ? ` · ${p.team_name}` : ""}</p>
                </div>
                <p className="font-mono text-[14px] font-bold text-amber-400 tabular-nums shrink-0">{p.goals}</p>
                {p.assists > 0 && (
                  <p className="text-[10px] font-mono text-slate-500 tabular-nums shrink-0">+{p.assists}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---- live match card (unchanged from original) ---- */

function LiveMatchCard({
  match: m, gamble, betStake, setBetStake,
}: {
  match: MatchCard; gamble: boolean; betStake: number | null; setBetStake: (n: number | null) => void
}) {
  const homePct = m.wp ? Math.round(m.wp.p_home * 100) : null
  const drawPct = m.wp ? Math.round(m.wp.p_draw * 100) : null
  const awayPct = m.wp ? Math.round(m.wp.p_away * 100) : null

  return (
    <Link href={`/match/${m.match_id}`}
      className="block rounded-2xl border border-edge bg-surface-2 shadow-e1 hover:border-emerald-500/30 transition-colors overflow-hidden">
      {/* Header */}
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
            <div><p className="text-[12px] font-mono tabular-nums font-bold text-emerald-400">{homePct}%</p><p className="text-[9px] text-slate-500">Home</p></div>
            <div><p className="text-[12px] font-mono tabular-nums font-bold text-slate-400">{drawPct}%</p><p className="text-[9px] text-slate-500">Draw</p></div>
            <div><p className="text-[12px] font-mono tabular-nums font-bold text-orange-400">{awayPct}%</p><p className="text-[9px] text-slate-500">Away</p></div>
          </div>
          <MiniSparkline data={m.sparkline} />
        </div>
      )}
      {/* Stats (fun) */}
      {!gamble && m.state && (
        <div className="px-4 py-2.5 grid grid-cols-3 gap-2 text-[10px] font-mono tabular-nums">
          {m.state.home_possession != null && (
            <div><p className="text-slate-600 mb-0.5">Possession</p><p className="text-slate-200">{Math.round(m.state.home_possession)} / {Math.round(m.state.away_possession || 0)}</p></div>
          )}
          {(m.state.home_shots != null || m.state.away_shots != null) && (
            <div><p className="text-slate-600 mb-0.5">Shots (on target)</p><p className="text-slate-200">{m.state.home_shots ?? 0}({m.state.home_shots_on_target ?? 0}) / {m.state.away_shots ?? 0}({m.state.away_shots_on_target ?? 0})</p></div>
          )}
          {m.state.home_xg != null && m.state.away_xg != null && (
            <div><p className="text-slate-600 mb-0.5">xG</p><p className="text-slate-200">{m.state.home_xg.toFixed(2)} / {m.state.away_xg.toFixed(2)}</p></div>
          )}
        </div>
      )}
      {/* Bet mode */}
      {gamble && (
        <div className="px-4 py-2.5" onClick={(e) => e.preventDefault()}>
          <BetSlip matchId={m.match_id} homeName={m.home_name} awayName={m.away_name} stake={betStake} setStake={setBetStake} />
        </div>
      )}
      <div className="px-4 py-2 border-t border-edge/40 flex items-center justify-between text-[9px] text-slate-600">
        <span className="uppercase tracking-wider">Group {m.group} · MD{m.matchday}</span>
        <span>Tap for full detail →</span>
      </div>
    </Link>
  )
}
