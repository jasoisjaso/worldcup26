"use client"

import { useEffect, useState } from "react"

/**
 * Live banner. Sits at the top of the /match page when the match is
 * actively in play, polls the live endpoint every 20s, shows the
 * current score + minute + how the model's win probability has
 * shifted since kickoff.
 *
 * Why this exists: the SSR verdict block renders the pre-kickoff
 * prediction once. Once the match goes live, a casual viewer sees
 * stale numbers without realising it. The banner makes the live
 * state authoritative: "Brazil now 87%, was 60% at KO" reads at a
 * glance and tells the user "trust the live prob, not the pre-match
 * verdict below".
 *
 * Calm UI rules (per the in-play UX research):
 * - No layout shift on update. Banner takes the same height in all
 *   states, including empty.
 * - No flashing. The number changes in place.
 * - Polling cadence 20s. Aligns with the backend's score_refresh
 *   tick window without hammering the proxy.
 */

interface LiveData {
  state: {
    status: string
    elapsed_min: number | null
    home_score: number
    away_score: number
  } | null
  history: Array<{
    elapsed_min: number
    p_home: number
    p_draw: number
    p_away: number
    event_label?: string | null
  }>
}

interface Props {
  matchId: string
  homeName: string
  awayName: string
  // Pre-kickoff probabilities for the delta vs live.
  kickoffProbs: { home_win: number; draw: number; away_win: number }
  // De-vigged market implied probabilities at kickoff. The book line during
  // a live match is itself live, but we typically don't keep refreshing odds
  // mid-game so the kickoff line is our best static baseline. Used to flag
  // when the live model materially disagrees with the price the book set.
  marketImplied?: { home_win?: number | null; draw?: number | null; away_win?: number | null }
}

const LIVE_STATUSES = new Set([
  "1H", "HT", "2H", "ET", "P", "LIVE", "live",
])

export function LiveBanner({
  matchId, homeName, awayName, kickoffProbs, marketImplied,
}: Props) {
  const [data, setData] = useState<LiveData | null>(null)

  useEffect(() => {
    let cancelled = false
    async function poll() {
      try {
        const res = await fetch(`/api/live/match/${matchId}/live`)
        if (!res.ok) return
        const j = (await res.json()) as LiveData
        if (!cancelled) setData(j)
      } catch { /* silent */ }
    }
    poll()
    const id = setInterval(poll, 20_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [matchId])

  const state = data?.state
  const isLive = !!state && LIVE_STATUSES.has(state.status)
  if (!isLive) return null

  // Pull the latest probability tick. The history list is appended every
  // backend tick with the model's current view conditioned on the score.
  const lastTick = data!.history?.[data!.history.length - 1]
  const live = lastTick
    ? { home_win: lastTick.p_home, draw: lastTick.p_draw, away_win: lastTick.p_away }
    : null

  // Pick the favoured outcome on the live model so the banner highlights
  // whichever way the match is leaning right now.
  const outcomes = live
    ? [
        { side: "home" as const, label: homeName,   live: live.home_win, ko: kickoffProbs.home_win },
        { side: "draw" as const, label: "the draw", live: live.draw,     ko: kickoffProbs.draw },
        { side: "away" as const, label: awayName,   live: live.away_win, ko: kickoffProbs.away_win },
      ]
    : []
  const top = outcomes.length ? [...outcomes].sort((a, b) => b.live - a.live)[0] : null
  const delta = top ? (top.live - top.ko) * 100 : 0
  const deltaTone =
    Math.abs(delta) < 3 ? "text-slate-400"
    : delta > 0 ? "text-emerald-300"
    : "text-amber-300"
  const deltaSign = delta >= 0 ? "+" : ""

  // Status pill label, casual phrasing for non-football audience.
  const statusLabel = (() => {
    const s = state!.status
    if (s === "HT") return "Half time"
    if (s === "ET") return "Extra time"
    if (s === "P")  return "Penalties"
    return state!.elapsed_min ? `${state!.elapsed_min}'` : s
  })()

  return (
    <div className="rounded-2xl border border-rose-700/40 bg-rose-950/15 ring-1 ring-rose-500/30 p-4 mb-5">
      <div className="flex items-baseline justify-between gap-2 mb-2">
        <div className="flex items-center gap-2">
          <span className="inline-block w-2 h-2 rounded-full bg-rose-400 animate-pulse" aria-hidden />
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-rose-300">
            Live
          </span>
        </div>
        <span className="text-[10px] font-mono tabular-nums text-rose-300/80">
          {statusLabel}
        </span>
      </div>
      <p className="text-[18px] font-bold text-slate-100 font-mono tabular-nums mb-2">
        {homeName} <span className="text-[22px] mx-2">{state!.home_score}-{state!.away_score}</span> {awayName}
      </p>
      {top && (
        <>
          <p className="text-[12px] text-slate-300 leading-relaxed mb-2">
            Model now sees{" "}
            <span className="font-bold text-slate-100">
              {top.side === "draw" ? "a draw" : `${top.label} to win`}
            </span>{" "}
            at{" "}
            <span className="font-bold font-mono tabular-nums text-slate-100">
              {Math.round(top.live * 100)}%
            </span>{" "}
            <span className={`font-mono tabular-nums ${deltaTone}`}>
              ({deltaSign}{delta.toFixed(0)}pt vs kickoff)
            </span>
            .
          </p>
          {/* Live edge readout vs the de-vigged kickoff market price. Uses the
              same bands as the verdict block: >=8% relative + >=5pt absolute is
              edge, >=4% relative + >=2pt absolute is small edge. Lets a viewer
              tell at a glance whether the pre-match price still has value at
              the live model prob, or has been overtaken by the actual scoreline. */}
          {(() => {
            const implied = top.side === "home" ? marketImplied?.home_win
                          : top.side === "draw" ? marketImplied?.draw
                          : marketImplied?.away_win
            if (implied == null || implied <= 0) return null
            const edgePts = (top.live - implied) * 100
            const edgePct = (top.live / implied - 1) * 100
            const strong = edgePct >= 8 && edgePts >= 5
            const small  = !strong && edgePct >= 4 && edgePts >= 2
            const off    = edgePts <= -5
            if (!strong && !small && !off) return null
            const label = strong ? "Live edge" : small ? "Small live edge" : "Now off"
            const tone  = strong ? "text-emerald-300" : small ? "text-emerald-300/70" : "text-amber-300"
            const text  = strong
              ? `Pre-match price on ${top.side === "draw" ? "the draw" : top.label} now looks well-priced for backers.`
              : small
              ? `Pre-match price on ${top.side === "draw" ? "the draw" : top.label} still holds a slim edge.`
              : `Pre-match price on ${top.side === "draw" ? "the draw" : top.label} has been overtaken by the live model.`
            return (
              <p className="text-[11px] leading-relaxed pt-2 border-t border-rose-700/30">
                <span className={`font-bold uppercase tracking-[0.18em] text-[9px] ${tone}`}>{label}.</span>{" "}
                <span className="text-slate-400">{text}</span>
              </p>
            )
          })()}
        </>
      )}
      {!top && (
        <p className="text-[12px] text-slate-400">Awaiting first live tick.</p>
      )}
    </div>
  )
}
