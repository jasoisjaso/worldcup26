"use client"
/**
 * Tiny live banner that sits ABOVE the TopBar title row.
 *
 * - Polls /api/proxy/live-summary every 30s
 * - Hidden completely when nothing is live AND no kickoff within 30 min
 * - Shows scoreline + minute for the first in-play match; "+N more" when there's
 *   more than one
 * - When idle but a kickoff is imminent, shows a softer amber "Kickoff in 12m"
 *   variant so power users notice and tab over
 *
 * Renders inline inside TopBar so the iOS safe-area-inset-top padding applied
 * to TopBar's outer div carries through automatically. No fixed-position
 * hacks, no z-index fights with the Dynamic Island.
 */
import { useEffect, useState } from "react"
import Link from "next/link"

interface TeamRef {
  code: string | null
  name: string
  flag_url: string | null
}
interface LiveMatch {
  id: string
  home: TeamRef
  away: TeamRef
  home_score: number
  away_score: number
  elapsed_min: number
  status: string
}
interface NextKickoff {
  id: string
  home: TeamRef
  away: TeamRef
  minutes_away: number | null
}
interface Summary {
  live_count: number
  live: LiveMatch[]
  next: NextKickoff | null
}

export function LiveTickerBar() {
  const [data, setData] = useState<Summary | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const r = await fetch("/api/proxy/live-summary", { cache: "no-store" })
        if (alive && r.ok) setData(await r.json())
      } catch {
        /* keep stale */
      }
    }
    tick()
    const iv = setInterval(tick, 30_000)
    return () => {
      alive = false
      clearInterval(iv)
    }
  }, [])

  if (!data) return null

  const showLive = data.live_count > 0
  const showSoon =
    !showLive && data.next && data.next.minutes_away != null && data.next.minutes_away <= 30 && data.next.minutes_away >= 0

  if (!showLive && !showSoon) return null

  if (showLive) {
    // Render EVERY live match, not just the first. The previous behaviour
    // ('+N more' badge) was the right idea but invisible to users who had
    // two games on the pitch at once. Each match is its own pill linking
    // to its own /match/[id] page; the parent strip scrolls horizontally
    // on overflow so we don't push the rest of the TopBar around.
    return (
      <div
        className="flex items-stretch gap-1 overflow-x-auto scrollbar-none px-2 py-1
                   bg-gradient-to-r from-rose-950/90 via-rose-900/80 to-rose-950/90
                   border-b border-rose-700/30"
      >
        <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-rose-200/80 shrink-0 pl-1 pr-2 self-center">
          <span className="w-1.5 h-1.5 bg-rose-300 rounded-full animate-pulse" aria-hidden />
          Live
        </span>
        {data.live.map((m) => {
          const homeLabel = (m.home.code || "").toUpperCase() || m.home.name.slice(0, 3).toUpperCase()
          const awayLabel = (m.away.code || "").toUpperCase() || m.away.name.slice(0, 3).toUpperCase()
          return (
            <Link
              key={m.id}
              href={`/match/${m.id}`}
              className="flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-semibold
                         bg-rose-950/40 hover:bg-rose-900/60 border border-rose-700/20
                         text-rose-50 shrink-0 transition-colors"
            >
              {m.home.flag_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.home.flag_url} alt="" className="w-3 h-2 rounded-[1px] object-cover" />
              )}
              <span className="font-mono tabular-nums">{homeLabel}</span>
              <span className="font-mono tabular-nums font-black text-white">
                {m.home_score}-{m.away_score}
              </span>
              <span className="font-mono tabular-nums">{awayLabel}</span>
              {m.away.flag_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={m.away.flag_url} alt="" className="w-3 h-2 rounded-[1px] object-cover" />
              )}
              <span className="text-rose-200/70 font-mono tabular-nums ml-0.5">{m.elapsed_min}&apos;</span>
            </Link>
          )
        })}
      </div>
    )
  }

  // Imminent kickoff
  const n = data.next!
  const home = n.home.name || (n.home.code || "").toUpperCase()
  const away = n.away.name || (n.away.code || "").toUpperCase()
  return (
    <Link
      href="/live"
      className="flex items-center justify-center gap-2 px-3 py-1.5 text-[11px] font-semibold
                 bg-gradient-to-r from-amber-950/70 to-amber-900/60
                 border-b border-amber-700/30 text-amber-100
                 hover:from-amber-900 hover:to-amber-800 transition-colors"
    >
      <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" aria-hidden />
      <span className="text-amber-200/90 uppercase tracking-wider text-[10px] font-bold">Soon</span>
      <span>
        {home} v {away} kicks off in {n.minutes_away}m
      </span>
    </Link>
  )
}
