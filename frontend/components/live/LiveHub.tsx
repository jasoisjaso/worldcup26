"use client"
/**
 * Live match hub — enriched: event timeline, in-play stats, smart betting.
 *
 * Polls /live/hub/enriched every 15s. Each card has a compact-by-default
 * layout (header + event ticker + WP). A "Show match stats" toggle expands
 * the deeper detail block (per-team stat bars, key-player face stack,
 * model shift narrative, swing narrative). That keeps the at-a-glance
 * scoreboard quiet while letting power users dig in.
 *
 * Bet mode toggles the right side into Smart Bet Slip (fair odds + edge +
 * Kelly sizing).
 */
import { useEffect, useState, useMemo, useRef } from "react"
import Link from "next/link"
import { MiniSparkline } from "@/components/match/MiniSparkline"
import { SmartBetSlip } from "@/components/live/SmartBetSlip"
import { EventTicker } from "@/components/live/EventTicker"
import { SwingNarrative } from "@/components/live/SwingNarrative"
import { ShootoutTracker } from "@/components/live/ShootoutTracker"
import { FollowBell } from "@/components/match/FollowBell"

/* ---- types ---- */

interface LiveEvent {
  elapsed: number; extra: number | null; type: string; detail: string
  player_name: string | null; assist_name: string | null; team_name: string | null
  // "Penalty Shootout" on shootout kicks — ShootoutTracker's filter needs it
  // because shootout kicks arrive with elapsed=120, same as ET penalties.
  comments?: string | null
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

interface TeamStats {
  possession_pct: number | null
  shots_total: number | null
  shots_on_target: number | null
  shots_off_target: number | null
  shots_blocked: number | null
  shots_inside_box: number | null
  shots_outside_box: number | null
  corners: number | null
  fouls: number | null
  offsides: number | null
  yellow_cards: number | null
  red_cards: number | null
  saves: number | null
  passes_total: number | null
  passes_accurate: number | null
  passes_pct: number | null
  xg: number | null
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
    // Penalty-shootout tiebreaker — non-null only when status in {"P","PEN"}.
    // Triggers the ShootoutTracker render below.
    shootout_home_score: number | null; shootout_away_score: number | null
  }
  wp: { p_home: number; p_draw: number; p_away: number } | null
  sparkline: Array<{ e: number; h: number; a: number }>
  events: LiveEvent[]
  api_prediction: ApiPrediction | null
  fair_odds: FairOdds
  implied_probs: ImpliedProbs
  key_players?: { home: KeyPlayer[]; away: KeyPlayer[] }
  live_stats?: {
    home: TeamStats | null
    away: TeamStats | null
    yellow_card_count: { home: number; away: number }
  }
}

interface HubData { live_count: number; matches: MatchCard[] }
interface UpcomingMatch {
  id: string; home_name: string; away_name: string
  home_flag: string | null; away_flag: string | null
  kickoff: string | null; group: string; matchday: number
}
// A match that should be on now (or just was) but isn't running normally —
// weather delay / postponement / abandonment. Rendered at the top of /live so
// a disrupted fixture never silently vanishes (MEX-ENG 2026-07-06 weather).
interface InterruptedMatch {
  id: string; home_name: string; away_name: string
  home_flag: string | null; away_flag: string | null
  kickoff: string | null; group: string; matchday: number
  interruption_status: "delayed" | "postponed" | "abandoned"
  interruption_reason: string | null
  partial_score: { home: number; away: number } | null
}
const INT_META: Record<
  string,
  { label: string; glyph: string; cls: string; ring: string; note: string }
> = {
  delayed: { label: "Delayed", glyph: "⏸", cls: "text-amber-300", ring: "border-amber-500/30", note: "Paused — waiting for restart" },
  postponed: { label: "Postponed", glyph: "↺", cls: "text-slate-300", ring: "border-slate-500/30", note: "Not going ahead as scheduled" },
  abandoned: { label: "Abandoned", glyph: "✕", cls: "text-rose-300", ring: "border-rose-500/30", note: "Called off — picks voided" },
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
  upcoming: { matches: UpcomingMatch[]; interrupted?: InterruptedMatch[] } | null
  completed: { matches: RecentMatch[] } | null
  topscores: { leaderboard: ScorerRow[] } | null
}) {
  const interrupted = upcoming?.interrupted ?? []
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

      {/* ---- DISRUPTED ---- weather delay / postponement / abandonment.
           Shown FIRST: a match that should be on now but isn't is the single
           most important thing a user checking /live needs to know. */}
      {interrupted.length > 0 && (
        <div className="space-y-2">
          {interrupted.map((m) => {
            const meta = INT_META[m.interruption_status] ?? INT_META.postponed
            return (
              <Link
                key={m.id}
                href={`/match/${m.id}`}
                className={`block rounded-2xl border ${meta.ring} bg-surface-2 shadow-e1 overflow-hidden hover:bg-surface-1 transition-colors`}
              >
                <div className="px-4 pt-3 pb-1 flex items-center gap-2">
                  <span className={`inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest ${meta.cls}`}>
                    <span aria-hidden>{meta.glyph}</span> {meta.label}
                  </span>
                  <span className="text-[11px] text-slate-500 truncate">{m.interruption_reason || meta.note}</span>
                </div>
                <div className="px-4 pb-3 flex items-center justify-center gap-3">
                  {m.home_flag && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.home_flag} alt="" className="w-7 h-5 rounded-[2px] object-cover" />
                  )}
                  <span className="text-[15px] font-bold text-white">{m.home_name}</span>
                  {m.partial_score ? (
                    <span className="font-mono text-[18px] font-black text-slate-300 tabular-nums px-1">
                      {m.partial_score.home}-{m.partial_score.away}
                    </span>
                  ) : (
                    <span className="text-slate-700 text-[12px] mx-1">v</span>
                  )}
                  <span className="text-[15px] font-bold text-white">{m.away_name}</span>
                  {m.away_flag && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={m.away_flag} alt="" className="w-7 h-5 rounded-[2px] object-cover" />
                  )}
                </div>
                <p className="px-4 pb-3 text-center text-[10px] text-slate-600">
                  Scheduled {localKickoff(m.kickoff)} AEST · Group {m.group} · MD{m.matchday}
                </p>
              </Link>
            )
          })}
        </div>
      )}

      {/* ---- LIVE MATCHES ---- */}
      {!noLive ? (
        <div className="space-y-4">
          {data.matches.map((m) => (
            <LiveMatchCard key={m.match_id} match={m} gamble={gamble} />
          ))}
        </div>
      ) : (
        <div className="rounded-2xl border border-edge bg-gradient-to-br from-surface-2 to-surface-1 shadow-e1 p-6">
          <div className="text-center">
            <div className="inline-flex items-center gap-2 mb-3 px-3 py-1 rounded-full bg-slate-800/50 border border-edge">
              <span className="w-1.5 h-1.5 rounded-full bg-slate-600" />
              <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">No matches in play</span>
            </div>
            {upcoming && upcoming.matches.length > 0 ? (() => {
              const next = upcoming.matches[0]
              const utc = (iso: string | null) =>
                iso ? new Date(iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso) ? iso : iso + "Z").getTime() : 0
              const minutesAway = Math.max(0, Math.round((utc(next.kickoff) - Date.now()) / 60000))
              return (
                <>
                  <p className="text-[12px] text-slate-500 uppercase tracking-wider mb-2">Next up</p>
                  <Link href={`/match/${next.id}`} className="block group">
                    <div className="flex items-center justify-center gap-3 mb-2 hover:opacity-80 transition-opacity">
                      {next.home_flag && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={next.home_flag} alt="" className="w-8 h-5.5 rounded-[2px] object-cover" />
                      )}
                      <span className="text-[16px] font-bold text-white">{next.home_name}</span>
                      <span className="text-slate-700 text-[12px] mx-1">v</span>
                      <span className="text-[16px] font-bold text-white">{next.away_name}</span>
                      {next.away_flag && (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={next.away_flag} alt="" className="w-8 h-5.5 rounded-[2px] object-cover" />
                      )}
                    </div>
                    <p className="text-[13px] text-emerald-400 font-mono tabular-nums">
                      Kicks off in {minutesAway > 90 ? `${Math.round(minutesAway / 60)}h ${minutesAway % 60}m` : `${minutesAway}m`}
                    </p>
                    <p className="text-[10px] text-slate-600 mt-1">{localKickoff(next.kickoff)} AEST · Group {next.group} · MD{next.matchday}</p>
                  </Link>
                </>
              )
            })() : (
              <p className="text-[14px] text-slate-400 font-semibold">All matchdays complete for now</p>
            )}
            <div className="mt-5 pt-5 border-t border-edge/40 flex items-center justify-center gap-4 text-[11px]">
              <Link href="/" className="text-emerald-400 hover:underline">All matches</Link>
              <span className="text-slate-700">·</span>
              <Link href="/value" className="text-emerald-400 hover:underline">Value board</Link>
              <span className="text-slate-700">·</span>
              <Link href="/winner" className="text-emerald-400 hover:underline">Outright odds</Link>
            </div>
          </div>
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
            <div className="flex items-center gap-1 shrink-0">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              {m.away_flag && <img src={m.away_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
            </div>
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

      {/* ---- JUST FINISHED ---- richer rows showing scorers + reds so the strip
           reads as a proper match report, not just a score */}
      {completed && completed.matches.length > 0 && (
        <div className="rounded-2xl border border-edge bg-surface-2 overflow-hidden">
          <div className="px-4 py-3 border-b border-edge/40">
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">Just finished</span>
          </div>
          <div className="divide-y divide-edge/30">
            {completed.matches.map((m: any) => (
              <Link key={m.id} href={`/match/${m.id}`} className="flex items-start gap-2.5 px-4 py-3 hover:bg-surface-1 transition-colors">
                <div className="flex items-center gap-1 shrink-0 pt-0.5">
                  {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
                  {m.away_flag && <img src={m.away_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[12px] text-slate-200 font-medium truncate flex-1">{m.home_name} v {m.away_name}</span>
                    <span className="text-[12px] font-mono font-bold text-white tabular-nums shrink-0">{m.home_score}-{m.away_score}</span>
                  </div>
                  {(m.scorer_line || m.red_cards > 0) && (
                    <p className="text-[10px] text-slate-500 truncate mt-0.5">
                      {m.scorer_line}
                      {m.red_cards > 0 && (
                        <span className="text-rose-400 ml-1.5 inline-flex items-center gap-1">
                          <span className="inline-block w-[7px] h-[10px] bg-rose-500 rounded-[1px]" aria-hidden />
                          {m.red_cards}
                        </span>
                      )}
                    </p>
                  )}
                </div>
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
  const [expanded, setExpanded] = useState(false)
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
      // Goal notification dedup tag includes the score so iOS Safari doesn't
      // collapse simultaneous goals across matches into one bubble. Previously
      // `tag: m.match_id` was per-match — fine for "same match, repeated goal
      // alert", but on a matchday with two simultaneous games and BOTH score
      // at the same moment, iOS would replace the first notification with
      // the second (same tag wins). Adding `:h-a` makes every goal-state
      // transition unique.
      if (h > prevHomeRef.current) {
        setFlashing(true)
        setGoalLabel(`${m.home_name} ${h}-${a}`)
        try {
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification(`GOAL! ${m.home_name}`, {
              body: `${m.home_name} ${h}-${a} ${m.away_name}`,
              tag: `${m.match_id}:${h}-${a}`,
            })
          }
        } catch { /* no-op */ }
      } else if (a > prevAwayRef.current) {
        setFlashing(true)
        setGoalLabel(`${m.away_name} ${h}-${a}`)
        try {
          if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
            new Notification(`GOAL! ${m.away_name}`, {
              body: `${m.home_name} ${h}-${a} ${m.away_name}`,
              tag: `${m.match_id}:${h}-${a}`,
            })
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
      {/* Header: teams + score + LIVE badge. Each team row has its OWN score
          right-aligned next to it so mobile readers can match team → score
          without having to count positions. Leading team's score is brighter
          + bolder, trailing team is dimmed. */}
      <Link href={`/match/${m.match_id}`} className="block px-4 pt-3.5 pb-3 border-b border-edge/40">
        {(() => {
          const hs = m.state.home_score
          const as_ = m.state.away_score
          const homeLeading = hs > as_
          const awayLeading = as_ > hs
          const row = (flag: string | null, name: string, score: number, isLeading: boolean, isOther: boolean) => (
            <div className="flex items-center gap-3">
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-6 h-4 rounded-[2px] object-cover shrink-0" />
              )}
              <span className={`flex-1 truncate text-[15px] font-bold ${isOther ? "text-slate-400" : "text-white"}`}>{name}</span>
              <span className={`font-mono text-[26px] tabular-nums font-black tabular-nums leading-none shrink-0 ${isLeading ? "text-emerald-300" : isOther ? "text-slate-500" : "text-white"}`}>
                {score}
              </span>
            </div>
          )
          // Status badge — explicit so "45'" never reads ambiguously as
          // "minute 45" when the match is actually at half time.
          const STATUS_LABEL: Record<string, string> = {
            "1H": "1st half", "HT": "Half time", "2H": "2nd half",
            "ET": "Extra time", "BT": "ET break", "P": "Penalties",
            "FT": "Full time", "AET": "After extra time", "PEN": "Penalties FT",
            "LIVE": "Live",
          }
          const statusLabel = STATUS_LABEL[m.state.status] ?? "Live"
          const isPaused = m.state.status === "HT" || m.state.status === "BT" || m.state.status === "FT" || m.state.status === "AET" || m.state.status === "PEN"
          return (
            <>
              {row(m.home_flag, m.home_name, hs, homeLeading, awayLeading)}
              <div className="mt-2">
                {row(m.away_flag, m.away_name, as_, awayLeading, homeLeading)}
              </div>
              <div className="flex items-center gap-1.5 mt-2">
                <span className={`w-1.5 h-1.5 rounded-full ${isPaused ? "bg-amber-400" : "bg-rose-500 animate-pulse"}`} />
                <span className={`text-[10px] font-bold uppercase tracking-widest ${isPaused ? "text-amber-300" : "text-rose-300"}`}>
                  {statusLabel}
                </span>
                <span className="text-[11px] text-slate-400 font-mono tabular-nums ml-1">{m.state.elapsed_min}&apos;</span>
                {/* Follow bell — sits inside the Link wrapper, span below
                    blocks the click from bubbling to the navigation. */}
                <span
                  className="ml-auto"
                  onClick={(e) => { e.stopPropagation(); e.preventDefault() }}
                >
                  <FollowBell matchId={m.match_id} />
                </span>
              </div>
            </>
          )
        })()}
      </Link>

      {/* Event ticker: goals + cards with team flag + player names */}
      {m.events.length > 0 && (
        <EventTicker
          events={m.events}
          homeName={m.home_name}
          awayName={m.away_name}
          homeFlag={m.home_flag}
          awayFlag={m.away_flag}
        />
      )}

      {/* Shootout tracker: dots row + per-kick log. Renders only while the
          match is in P (shootout in progress) or PEN (just decided). The
          score row above keeps the regulation+ET score; this block adds
          the "(4-3 pens)" tiebreaker view. */}
      {(m.state.status === "P" || m.state.status === "PEN") && (
        <ShootoutTracker
          homeName={m.home_name}
          awayName={m.away_name}
          homeFlag={m.home_flag}
          awayFlag={m.away_flag}
          shootoutHomeScore={m.state.shootout_home_score}
          shootoutAwayScore={m.state.shootout_away_score}
          regulationHome={m.state.home_score}
          regulationAway={m.state.away_score}
          events={m.events}
          status={m.state.status}
        />
      )}

      {/* Key player face stacks. Each side has a clear team header (flag +
          name) so users know whose players these are; player names sit under
          each photo so faces aren't a guessing game. Hidden gracefully when
          a team isn't harvested yet. Behind the expand toggle. */}
      {expanded && m.key_players && (m.key_players.home.length > 0 || m.key_players.away.length > 0) && (
        <div className="px-4 py-3 border-b border-edge/20">
          <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Players to watch</p>
          <div className="grid grid-cols-2 gap-3">
            {[
              { side: "home", flag: m.home_flag, label: m.home_name, players: m.key_players.home },
              { side: "away", flag: m.away_flag, label: m.away_name, players: m.key_players.away },
            ].map((side) => (
              <div key={side.side} className="min-w-0">
                <div className="flex items-center gap-1.5 mb-2 min-w-0">
                  {side.flag && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={side.flag} alt="" className="w-4 h-3 rounded-[1px] object-cover shrink-0" />
                  )}
                  <p className="text-[11px] font-bold text-slate-200 truncate">{side.label}</p>
                </div>
                {side.players.length === 0 ? (
                  <p className="text-[10px] text-slate-700">No stats yet</p>
                ) : (
                  <div className="flex items-start gap-2">
                    {side.players.slice(0, 3).map((p) => (
                      <Link
                        key={p.id}
                        href={`/player/${p.id}?from=/live`}
                        title={`${p.name} · ${p.goals}g ${p.assists}a`}
                        className="group relative flex flex-col items-center w-[58px]"
                      >
                        <div className="relative">
                          {p.photo_url ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={p.photo_url}
                              alt={p.name}
                              className="w-10 h-10 rounded-full object-cover ring-1 ring-white/10 bg-slate-800 group-hover:ring-emerald-400/60 transition-shadow"
                            />
                          ) : (
                            <span className="w-10 h-10 rounded-full bg-slate-800 ring-1 ring-white/10 inline-block" />
                          )}
                          {p.goals > 0 && (
                            <span className="absolute -bottom-1 -right-1 bg-amber-500 text-amber-950 font-black text-[8px] w-4 h-4 rounded-full flex items-center justify-center ring-1 ring-surface-2">
                              {p.goals}
                            </span>
                          )}
                        </div>
                        <p className="text-[9px] text-slate-400 mt-1 text-center leading-tight w-full truncate group-hover:text-emerald-300">
                          {p.name.split(" ").slice(-1)[0]}
                        </p>
                      </Link>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
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

      {/* What just happened: auto-narrative on big WP swings (expanded only) */}
      {expanded && m.wp && m.sparkline.length >= 2 && (
        <SwingNarrative
          sparkline={m.sparkline}
          events={m.events}
          homeName={m.home_name}
          awayName={m.away_name}
        />
      )}

      {/* Model trend — kickoff probability vs now, narrating how the match
          has shifted our model. Hidden until expanded. */}
      {expanded && m.wp && m.sparkline.length >= 2 && (() => {
        const open = m.sparkline[0]
        const now = m.sparkline[m.sparkline.length - 1]
        const dHome = Math.round((now.h - open.h) * 100)
        const dAway = Math.round((now.a - open.a) * 100)
        const biggest = Math.abs(dHome) >= Math.abs(dAway) ? dHome : dAway
        const teamShifted = Math.abs(dHome) >= Math.abs(dAway) ? m.home_name : m.away_name
        const isPositive = biggest > 0
        if (Math.abs(biggest) < 5) return null
        return (
          <div className="px-4 py-2 border-b border-edge/20 text-[11px] text-slate-400">
            <span className="text-slate-600 uppercase tracking-wider text-[9px] font-bold mr-2">Model shift</span>
            <span className={isPositive ? "text-emerald-300" : "text-rose-300"}>
              {teamShifted} {isPositive ? "+" : ""}{biggest}pt
            </span>
            <span className="text-slate-600"> since kickoff</span>
          </div>
        )
      })()}

      {/* Full live stats panel OR gamble. Stats are ALWAYS visible — they
          are the value. Only the swing narrative, key players and model
          shift sit behind the expand toggle. */}
      {!gamble ? (
        <LiveStatsPanel match={m} />
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

      {/* Expand / Collapse toggle. Quiet by default so the at-a-glance
          scoreboard breathes; one tap reveals stats / key players / swings. */}
      {!gamble && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="w-full px-4 py-2 border-t border-edge/40 text-[10px] font-bold uppercase tracking-widest text-slate-500 hover:text-emerald-300 hover:bg-surface-3 transition-colors"
        >
          {expanded ? "Hide match details ↑" : "Show match details ↓"}
        </button>
      )}

      <div className="px-4 py-2 border-t border-edge/40 flex items-center justify-between text-[9px] text-slate-600">
        <span className="uppercase tracking-wider">Group {m.group} · MD{m.matchday}</span>
        <Link href={`/match/${m.match_id}`} className="hover:text-emerald-400">Full match page →</Link>
      </div>
    </div>
  )
}


/* ---- live stats panel: home-vs-away bar for every tracked stat ---- */

function StatBar({
  label, home, away, format = "int", unit = "",
}: {
  label: string
  home: number | null | undefined
  away: number | null | undefined
  format?: "int" | "float" | "pct"
  unit?: string
}) {
  if (home == null && away == null) return null
  const h = home ?? 0
  const a = away ?? 0
  const total = h + a
  const homePct = total > 0 ? (h / total) * 100 : 50
  const fmt = (v: number | null | undefined) => {
    if (v == null) return "-"
    if (format === "float") return v.toFixed(2)
    if (format === "pct") return `${Math.round(v)}%`
    return String(Math.round(v))
  }
  const homeBetter = h > a
  const awayBetter = a > h
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-mono tabular-nums">
        <span className={`${homeBetter ? "text-white font-bold" : "text-slate-400"}`}>{fmt(home)}{unit}</span>
        <span className="text-[9px] text-slate-600 uppercase tracking-wider font-sans">{label}</span>
        <span className={`${awayBetter ? "text-white font-bold" : "text-slate-400"}`}>{fmt(away)}{unit}</span>
      </div>
      <div className="flex h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="bg-emerald-500/70" style={{ width: `${homePct}%` }} />
        <div className="bg-orange-500/70" style={{ width: `${100 - homePct}%` }} />
      </div>
    </div>
  )
}

function LiveStatsPanel({ match: m }: { match: MatchCard }) {
  const hs = m.live_stats?.home ?? null
  const as_ = m.live_stats?.away ?? null
  const ycCount = m.live_stats?.yellow_card_count ?? { home: 0, away: 0 }

  // Fallback to LiveMatchState fields when MatchStatistics hasn't been written yet.
  const possH = hs?.possession_pct ?? m.state.home_possession ?? null
  const possA = as_?.possession_pct ?? m.state.away_possession ?? null
  const shotsH = hs?.shots_total ?? m.state.home_shots ?? null
  const shotsA = as_?.shots_total ?? m.state.away_shots ?? null
  const sotH = hs?.shots_on_target ?? m.state.home_shots_on_target ?? null
  const sotA = as_?.shots_on_target ?? m.state.away_shots_on_target ?? null
  const xgH = hs?.xg ?? m.state.home_xg ?? null
  const xgA = as_?.xg ?? m.state.away_xg ?? null

  // Yellow cards: stats row first, MatchEvent count fallback.
  const ycH = hs?.yellow_cards ?? ycCount.home
  const ycA = as_?.yellow_cards ?? ycCount.away

  const hasAny =
    possH != null || possA != null ||
    shotsH != null || xgH != null ||
    (hs?.corners ?? null) != null || (hs?.fouls ?? null) != null ||
    ycH > 0 || ycA > 0

  if (!hasAny) {
    return (
      <div className="px-4 py-3 text-[11px] text-slate-600 text-center">
        Stats arrive once the match has played a few minutes.
      </div>
    )
  }

  return (
    <div className="px-4 py-3 space-y-2.5 border-t border-edge/30">
      <p className="text-[9px] font-bold uppercase tracking-[0.18em] text-slate-500 -mb-0.5">Match stats</p>
      <StatBar label="Possession" home={possH} away={possA} format="pct" />
      <StatBar label="Shots" home={shotsH} away={shotsA} />
      <StatBar label="Shots on target" home={sotH} away={sotA} />
      {xgH != null && <StatBar label="Expected goals" home={xgH} away={xgA} format="float" />}
      {(hs?.corners != null || as_?.corners != null) && (
        <StatBar label="Corners" home={hs?.corners} away={as_?.corners} />
      )}
      {(hs?.fouls != null || as_?.fouls != null) && (
        <StatBar label="Fouls" home={hs?.fouls} away={as_?.fouls} />
      )}
      {(hs?.offsides != null || as_?.offsides != null) && (
        <StatBar label="Offsides" home={hs?.offsides} away={as_?.offsides} />
      )}
      {(ycH > 0 || ycA > 0) && (
        <StatBar label="Yellow cards" home={ycH} away={ycA} />
      )}
      {(m.state.home_red_cards > 0 || m.state.away_red_cards > 0) && (
        <StatBar label="Red cards" home={m.state.home_red_cards} away={m.state.away_red_cards} />
      )}
      {(hs?.saves != null || as_?.saves != null) && (
        <StatBar label="Saves" home={hs?.saves} away={as_?.saves} />
      )}
      {(hs?.passes_pct != null || as_?.passes_pct != null) && (
        <StatBar label="Pass accuracy" home={hs?.passes_pct} away={as_?.passes_pct} format="pct" />
      )}
    </div>
  )
}
