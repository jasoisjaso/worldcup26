"use client"
/**
 * Live match hub — enriched: event timeline, api-football comparison, smart betting.
 *
 * Polls /api/live/hub/enriched every 15s. Shows:
 *  - Live match cards with event ticker (goal scorers, cards)
 *  - Key player face stacks per team (uses harvested PlayerProfile + stats)
 *  - Goal flash animation when score changes between polls + browser push
 *  - api-football prediction vs our model side-by-side
 *  - Smart bet slip: real fair odds, edge %, Kelly sizing
 *  - Coming up, Just finished, Golden Boot mini
 *  - Fun / Bet toggle per card
 */
import { useEffect, useState, useMemo, useRef } from "react"
import Link from "next/link"
import { MiniSparkline } from "@/components/match/MiniSparkline"
import { SmartBetSlip } from "@/components/live/SmartBetSlip"
import { EventTicker } from "@/components/live/EventTicker"
import { SwingNarrative } from "@/components/live/SwingNarrative"

/* ---- types ---- */

interface LiveEvent {
  elapsed: number; extra: number | null; type: string; detail: string
  player_name: string | null; assist_name: string | null; team_name: string | null
}

interface ApiPrediction {
  winner_name?: string; winner_comment?: string; advice?: string
  pct_home?: string; pct_draw?: string; pct_away?: string
  form_home?: string; form_away?: string; h2h_home?: string; h2h_away?: string
}

interface FairOdds { home: number | null; draw: number | null; away: number | null }
interface ImpliedProbs { home: number | null; draw: number | null; away: number | null }

interface KeyPlayer {
  id: number; name: string; photo_url: string | null
  position: string | null; goals: number; assists: number
}

interface MatchCard {
  match_id: string; group: string; matchday: number
  home_code: string | null; away_code: string | null
  home_name: string; away_name: string
  home_flag: string | null; away_flag: string | null
  kickoff: string | null
  state: {
    status: string; elapsed_min: number; home_score: number; away_score: number
    home_red_cards: number; away_red_cards: number
    home_possession: number | null; away_possession: number | null
    home_shots: number | null; away_shots: number | null
    home_shots_on_target: number | null; away_shots_on_target: number | null
    home_xg: number | null; away_xg: number | null
  }
  wp: { p_home: number; p_draw: number; p_away: number } | null
  sparkline: Array<{ e: number; h: number; a: number }>
  events: LiveEvent[]
  api_prediction: ApiPrediction | null
  fair_odds: FairOdds
  implied_probs: ImpliedProbs
  key_players?: { home: KeyPlayer[]; away: KeyPlayer[] }
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
  name: string; nationality?: string; photo?: string; goals: number; assists: number; team_name?: string
}

/* ---- helpers ---- */
function toUtcDate(iso: string): Date {
  const hasOffset = iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)
  return new Date(hasOffset ? iso : iso + "Z")
}
function localKickoff(iso: string | null): string {
  if (!iso) return ""
  try {
    return toUtcDate(iso).toLocaleTimeString("en-AU", {
      timeZone: "Australia/Brisbane",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch { return "" }
}
function pct(s: string | undefined): number {
  if (!s) return 0
  return parseInt(s.replace("%", "")) || 0
}

/* ---- main ---- */

export function LiveHub({
  initialData, upcoming, completed, topscores,
}: {
  initialData: HubData | null
  upcoming: { matches: UpcomingMatch[] } | null
  completed: { matches: RecentMatch[] } | null
  topscores: { leaderboard: ScorerRow[] } | null
}) {
  const [data, setData] = useState<HubData | null>(initialData)
  const [gamble, setGamble] = useState(false)

  useEffect(() => {
    const iv = setInterval(async () => {
      try {
        const r = await fetch("/api/live/hub/enriched")
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
        <div className="space-y-4">
          {data.matches.map((m) => (
            <LiveMatchCard key={m.match_id} match={m} gamble={gamble} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-edge bg-surface-2 p-8 text-center">
          <p className="text-[16px] text-slate-400 font-semibold mb-1.5">No live matches right now</p>
          <p className="text-[12px] text-slate-600">
            This page lights up when World Cup fixtures are in play.<br />
            <Link href="/" className="text-emerald-400 hover:underline">Browse upcoming matches →</Link>
          </p>
        </div>
      )}

      {/* ---- COMING UP ---- split into "next 3 hours" vs "later" so the casual
           reader can tell at a glance what's about to start without scanning kickoffs */}
      {upcoming && upcoming.matches.length > 0 && (() => {
        const horizon = Date.now() + 3 * 60 * 60 * 1000
        const toUtc = (iso: string | null) =>
          iso ? new Date(iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z").getTime() : Infinity
        const soon = upcoming.matches.filter((m) => toUtc(m.kickoff) <= horizon)
        const later = upcoming.matches.filter((m) => toUtc(m.kickoff) > horizon)
        const renderRow = (m: typeof upcoming.matches[number]) => (
          <Link key={m.id} href={`/match/${m.id}`} className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface-1 transition-colors">
            {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
            <span className="text-[12px] text-slate-200 font-medium truncate flex-1">{m.home_name} v {m.away_name}</span>
            <span className="text-[11px] font-mono text-slate-500 tabular-nums shrink-0">{localKickoff(m.kickoff)}</span>
          </Link>
        )
        return (
          <div className="rounded-2xl border border-edge bg-surface-2 overflow-hidden">
            <div className="px-4 py-3 border-b border-edge/40 flex items-center gap-2">
              <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Coming up</span>
              <span className="w-1.5 h-1.5 bg-amber-500 rounded-full" />
              <span className="text-[9px] font-mono text-slate-600 ml-auto">AEST (Brisbane)</span>
            </div>
            {soon.length > 0 && (
              <>
                <p className="px-4 pt-3 pb-1 text-[9px] font-bold uppercase tracking-widest text-amber-400/80">Next 3 hours</p>
                <div className="divide-y divide-edge/30">{soon.map(renderRow)}</div>
              </>
            )}
            {later.length > 0 && (
              <>
                <p className={`px-4 pt-3 pb-1 text-[9px] font-bold uppercase tracking-widest text-slate-600 ${soon.length > 0 ? "border-t border-edge/30 mt-1" : ""}`}>Later</p>
                <div className="divide-y divide-edge/30">{later.map(renderRow)}</div>
              </>
            )}
          </div>
        )
      })()}

      {/* ---- JUST FINISHED ---- */}
      {completed && completed.matches.length > 0 && (
        <div className="rounded-2xl border border-edge bg-surface-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-edge/40"><span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Just finished</span></div>
          <div className="divide-y divide-edge/30">
            {completed.matches.map((m) => (
              <Link key={m.id} href={`/match/${m.id}`} className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface-1 transition-colors">
                {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
                <span className="text-[12px] text-slate-200 font-medium truncate flex-1">{m.home_name} v {m.away_name}</span>
                <span className="text-[12px] font-mono font-bold text-white tabular-nums shrink-0">{m.home_score}–{m.away_score}</span>
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
                {p.photo ? <img src={p.photo} alt="" className="w-6 h-6 rounded-full ring-1 ring-white/10 object-cover shrink-0" /> : <span className="w-6 h-6 rounded-full bg-surface-1 shrink-0" />}
                <div className="flex-1 min-w-0"><p className="text-[11px] font-semibold text-slate-100 truncate">{p.name}</p><p className="text-[10px] text-slate-500 truncate">{p.nationality}{p.team_name ? ` · ${p.team_name}` : ""}</p></div>
                <p className="font-mono text-[14px] font-bold text-amber-400 tabular-nums shrink-0">{p.goals}</p>
                {p.assists > 0 && <p className="text-[10px] font-mono text-slate-500 tabular-nums shrink-0">+{p.assists}</p>}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

/* ---- live match card ---- */

function LiveMatchCard({ match: m, gamble }: { match: MatchCard; gamble: boolean }) {
  const homePct = m.wp ? Math.round(m.wp.p_home * 100) : null
  const drawPct = m.wp ? Math.round(m.wp.p_draw * 100) : null
  const awayPct = m.wp ? Math.round(m.wp.p_away * 100) : null

  // Edge: our model vs market implied (for smart bet slip)
  const edge = useMemo(() => {
    if (!m.wp || !m.implied_probs?.home) return null
    return {
      home: Math.round((m.wp.p_home - (m.implied_probs.home ?? 0)) * 100),
      draw: Math.round((m.wp.p_draw - (m.implied_probs.draw ?? 0)) * 100),
      away: Math.round((m.wp.p_away - (m.implied_probs.away ?? 0)) * 100),
    }
  }, [m.wp, m.implied_probs])

  // Goal flash: detect score deltas between polls. Pulse a green ring for 4s
  // and fire a browser notification if the user granted permission.
  const prevHomeRef = useRef<number | null>(null)
  const prevAwayRef = useRef<number | null>(null)
  const [flashing, setFlashing] = useState(false)
  const [goalLabel, setGoalLabel] = useState<string | null>(null)
  useEffect(() => {
    const h = m.state.home_score
    const a = m.state.away_score
    if (prevHomeRef.current != null && prevAwayRef.current != null) {
      if (h > prevHomeRef.current) {
        setFlashing(true)
        setGoalLabel(`${m.home_name} ${h}-${a}`)
        try {
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification(`GOAL! ${m.home_name}`, { body: `${m.home_name} ${h}-${a} ${m.away_name}`, tag: m.match_id })
          }
        } catch { /* no-op */ }
      } else if (a > prevAwayRef.current) {
        setFlashing(true)
        setGoalLabel(`${m.away_name} ${h}-${a}`)
        try {
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification(`GOAL! ${m.away_name}`, { body: `${m.home_name} ${h}-${a} ${m.away_name}`, tag: m.match_id })
          }
        } catch { /* no-op */ }
      }
    }
    prevHomeRef.current = h
    prevAwayRef.current = a
    if (flashing) {
      const t = setTimeout(() => { setFlashing(false); setGoalLabel(null) }, 4500)
      return () => clearTimeout(t)
    }
  }, [m.state.home_score, m.state.away_score, m.home_name, m.away_name, m.match_id, flashing])

  return (
    <div className={`rounded-2xl border bg-surface-2 shadow-e1 overflow-hidden transition-shadow ${flashing ? "border-emerald-400/80 shadow-[0_0_30px_rgba(16,185,129,0.45)] animate-pulse" : "border-edge"}`}>
      {flashing && goalLabel && (
        <div className="px-4 py-1.5 bg-emerald-500 text-emerald-950 font-black text-[11px] tracking-widest uppercase text-center">
          ⚽︎ Goal! {goalLabel}
        </div>
      )}
      {/* Header: teams + score + LIVE badge */}
      <Link href={`/match/${m.match_id}`} className="block px-4 pt-3.5 pb-3 border-b border-edge/40">
        <div className="flex items-center justify-between">
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
            <p className="font-mono text-[28px] tabular-nums font-black text-white leading-none">{m.state.home_score}–{m.state.away_score}</p>
            <div className="flex items-center gap-1.5 justify-end mt-0.5">
              <span className="w-1.5 h-1.5 bg-rose-500 rounded-full animate-pulse" />
              <span className="text-[11px] text-slate-400 font-mono tabular-nums">{m.state.elapsed_min}&apos;</span>
            </div>
          </div>
        </div>
      </Link>

      {/* Event ticker: goals + cards with player names */}
      {m.events.length > 0 && (
        <EventTicker events={m.events} homeName={m.home_name} awayName={m.away_name} />
      )}

      {/* Key player face stacks — top contributors per team. Hidden gracefully
          when a team isn't harvested yet (no rows = nothing to show). */}
      {m.key_players && (m.key_players.home.length > 0 || m.key_players.away.length > 0) && (
        <div className="px-4 py-2.5 border-b border-edge/20 grid grid-cols-2 gap-3">
          {[
            { side: "home", code: m.home_code, label: m.home_name, players: m.key_players.home },
            { side: "away", code: m.away_code, label: m.away_name, players: m.key_players.away },
          ].map((side) => (
            <div key={side.side} className="min-w-0">
              <p className="text-[9px] text-slate-600 uppercase tracking-wider mb-1.5 truncate">{side.label}</p>
              {side.players.length === 0 ? (
                <p className="text-[10px] text-slate-700">No stats yet</p>
              ) : (
                <div className="flex items-center gap-1.5">
                  {side.players.slice(0, 3).map((p) => (
                    <Link
                      key={p.id}
                      href={`/player/${p.id}?from=/live`}
                      title={`${p.name} · ${p.goals}g ${p.assists}a`}
                      className="group relative"
                    >
                      {p.photo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={p.photo_url}
                          alt={p.name}
                          className="w-8 h-8 rounded-full object-cover ring-1 ring-white/10 bg-slate-800 group-hover:ring-emerald-400/60 transition-shadow"
                        />
                      ) : (
                        <span className="w-8 h-8 rounded-full bg-slate-800 ring-1 ring-white/10 inline-block" />
                      )}
                      {p.goals > 0 && (
                        <span className="absolute -bottom-1 -right-1 bg-amber-500 text-amber-950 font-black text-[8px] w-3.5 h-3.5 rounded-full flex items-center justify-center ring-1 ring-surface-2">
                          {p.goals}
                        </span>
                      )}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      )}

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

      {/* What just happened: auto-narrative on big WP swings */}
      {m.wp && m.sparkline.length >= 2 && (
        <SwingNarrative
          sparkline={m.sparkline}
          events={m.events}
          homeName={m.home_name}
          awayName={m.away_name}
        />
      )}

      {/* api-football prediction vs our model comparison */}
      {m.api_prediction && m.wp && (
        <div className="px-4 py-2 border-b border-edge/20 grid grid-cols-2 gap-3 text-[10px]">
          <div>
            <p className="text-slate-600 mb-0.5">API-Football</p>
            <p className="text-white font-mono tabular-nums">
              <span className="text-emerald-400">{pct(m.api_prediction.pct_home)}%</span>
              {" / "}<span className="text-slate-400">{pct(m.api_prediction.pct_draw)}%</span>
              {" / "}<span className="text-orange-400">{pct(m.api_prediction.pct_away)}%</span>
            </p>
          </div>
          <div>
            <p className="text-slate-600 mb-0.5">Our model</p>
            <p className="text-white font-mono tabular-nums">
              <span className="text-emerald-400">{homePct}%</span>
              {" / "}<span className="text-slate-400">{drawPct}%</span>
              {" / "}<span className="text-orange-400">{awayPct}%</span>
            </p>
          </div>
        </div>
      )}

      {/* Fun stats OR gamble */}
      {!gamble ? (
        m.state && (
          <div className="px-4 py-2.5 grid grid-cols-3 gap-2 text-[10px] font-mono tabular-nums">
            {m.state.home_possession != null && (
              <div><p className="text-slate-600 mb-0.5">Possession</p><p className="text-slate-200">{Math.round(m.state.home_possession)} / {Math.round(m.state.away_possession ?? 0)}</p></div>
            )}
            {(m.state.home_shots != null) && (
              <div><p className="text-slate-600 mb-0.5">Shots (on target)</p><p className="text-slate-200">{m.state.home_shots ?? 0}({m.state.home_shots_on_target ?? 0}) / {m.state.away_shots ?? 0}({m.state.away_shots_on_target ?? 0})</p></div>
            )}
            {m.state.home_xg != null && (
              <div><p className="text-slate-600 mb-0.5">xG</p><p className="text-slate-200">{m.state.home_xg.toFixed(2)} / {(m.state.away_xg ?? 0).toFixed(2)}</p></div>
            )}
          </div>
        )
      ) : (
        <div className="px-4 py-2.5">
          <SmartBetSlip
            matchId={m.match_id}
            homeName={m.home_name}
            awayName={m.away_name}
            fairOdds={m.fair_odds}
            ourProbs={m.wp ? { home: m.wp.p_home, draw: m.wp.p_draw, away: m.wp.p_away } : null}
            edge={edge}
          />
        </div>
      )}

      <div className="px-4 py-2 border-t border-edge/40 flex items-center justify-between text-[9px] text-slate-600">
        <span className="uppercase tracking-wider">Group {m.group} · MD{m.matchday}</span>
        <Link href={`/match/${m.match_id}`} className="hover:text-emerald-400">Full detail →</Link>
      </div>
    </div>
  )
}
