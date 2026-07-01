"use client"
import { useEffect, useRef, useState } from "react"

interface LiveState {
  home_score: number
  away_score: number
  elapsed_min: number
  status_code: string
}

/**
 * Client-side live-score self-poller. Renders the current live scoreline for
 * a single match and refreshes it every N seconds from /api/live/summary.
 *
 * Ships two variants:
 *   - "hero"  → the NextUpHero centre column (larger, rose accent)
 *   - "card"  → the MatchCard centre column (compact pill)
 *
 * Why polling instead of a websocket / SSE: the backend already exposes an SSE
 * stream at /live/match/{id}/stream, but the homepage renders many cards at
 * once and a single /live/summary poll covers every live match in the
 * tournament with one request. Server load stays flat regardless of card count.
 *
 * Why /live/summary and not /live/match/{id}/live per pill: same reason — one
 * fetch across all mounted instances via a module-level fan-in cache, so a
 * page with 3 live matches during a group-stage window still makes one
 * outbound request every 20s.
 */

// Shared fan-in cache so N mounted <LiveScoreLive/> instances issue ONE poll
// each cycle. Cleared on unmount of the last subscriber.
type Sub = (matchId: string, next: LiveState | null) => void
const _subs = new Set<Sub>()
let _timer: ReturnType<typeof setInterval> | null = null
let _inFlight = false

// Same-origin path — the Next app proxies /api → backend, so the browser
// can hit this without CORS. Falls back to gracefully doing nothing on error.
async function pollOnce() {
  if (_inFlight) return
  _inFlight = true
  try {
    const res = await fetch("/api/live/summary", { cache: "no-store" })
    if (!res.ok) return
    const data: {
      live: Array<{ id: string; home_score: number; away_score: number; elapsed_min: number; status: string }>
    } = await res.json()
    const byId = new Map<string, LiveState>()
    for (const l of data.live) {
      byId.set(l.id, {
        home_score: l.home_score,
        away_score: l.away_score,
        elapsed_min: l.elapsed_min,
        status_code: l.status,
      })
    }
    for (const fn of Array.from(_subs)) {
      for (const [id, state] of Array.from(byId.entries())) fn(id, state)
    }
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    void byId
  } catch {
    /* silent — next tick will retry */
  } finally {
    _inFlight = false
  }
}

function subscribe(sub: Sub) {
  _subs.add(sub)
  if (_timer === null) {
    _timer = setInterval(pollOnce, 20_000)
    // Kick off an immediate poll so newly-mounted pills get fresh data within
    // ~1s of first paint (SSR gave us initial state so this is a soft update).
    void pollOnce()
  }
  return () => {
    _subs.delete(sub)
    if (_subs.size === 0 && _timer !== null) {
      clearInterval(_timer)
      _timer = null
    }
  }
}

function label(status_code: string, elapsed_min: number, variant: "hero" | "card") {
  if (status_code === "HT") return "Half-time"
  if (status_code === "BT") return variant === "hero" ? "Break · extra time" : "ET break"
  if (status_code === "P") return variant === "hero" ? "Penalties" : "PEN"
  if (status_code === "ET") return variant === "hero" ? `${elapsed_min}' · ET` : `${elapsed_min}' ET`
  return `${elapsed_min}'`
}

export function LiveScoreLive({
  matchId,
  initial,
  variant,
}: {
  matchId: string
  initial: LiveState
  variant: "hero" | "card"
}) {
  const [state, setState] = useState<LiveState>(initial)
  const gotUpdate = useRef(false)

  useEffect(() => {
    const unsub = subscribe((id, next) => {
      if (id === matchId && next) {
        gotUpdate.current = true
        setState(next)
      }
      // If __prune__ is broadcast and we never got our own id in this cycle,
      // the match has gone final — freeze on last known state. The SSR pass
      // will pick up match.status=complete on next page load.
    })
    return unsub
  }, [matchId])

  if (variant === "hero") {
    return (
      <>
        <p className="text-[10px] font-black uppercase tracking-widest text-rose-300">Live</p>
        <p className="text-[26px] sm:text-[30px] font-display font-black text-white leading-none tabular-nums mt-1 whitespace-nowrap">
          {state.home_score}<span className="text-slate-600 px-1">-</span>{state.away_score}
        </p>
        <p className="text-[11px] font-bold text-rose-300/90 mt-1 tabular-nums whitespace-nowrap">
          {label(state.status_code, state.elapsed_min, "hero")}
        </p>
      </>
    )
  }

  return (
    <div className="flex flex-col items-center">
      <span className="inline-flex items-center gap-1 text-[9px] font-black uppercase tracking-widest px-1.5 py-0.5 rounded border bg-rose-500/15 text-rose-300 border-rose-500/30">
        <span className="w-1 h-1 bg-rose-400 rounded-full animate-pulse" aria-hidden />
        Live
      </span>
      <p className="text-[20px] font-black text-white tabular-nums leading-tight mt-1 whitespace-nowrap">
        {state.home_score}-{state.away_score}
      </p>
      <p className="text-[9px] font-bold text-rose-300/80 tabular-nums mt-0.5 whitespace-nowrap">
        {label(state.status_code, state.elapsed_min, "card")}
      </p>
    </div>
  )
}
