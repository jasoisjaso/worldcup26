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
    const m = data.live[0]
    const homeLabel = (m.home.code || "").toUpperCase() || m.home.name.slice(0, 3).toUpperCase()
    const awayLabel = (m.away.code || "").toUpperCase() || m.away.name.slice(0, 3).toUpperCase()
    return (
      <Link
        href={`/match/${m.id}`}
        className="flex items-center justify-center gap-2 px-3 py-1.5 text-[11px] font-semibold
                   bg-gradient-to-r from-rose-950/90 via-rose-900/80 to-rose-950/90
                   border-b border-rose-700/30 text-rose-50
                   hover:from-rose-900 hover:to-rose-900 transition-colors"
      >
        <span className="w-1.5 h-1.5 bg-rose-300 rounded-full animate-pulse" aria-hidden />
        <span className="text-rose-200/80 uppercase tracking-wider text-[10px] font-bold">Live</span>
        {m.home.flag_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={m.home.flag_url} alt="" className="w-3.5 h-2.5 rounded-[1px] object-cover" />
        )}
        <span className="font-mono tabular-nums">{homeLabel}</span>
        <span className="font-mono tabular-nums font-black text-white">
          {m.home_score}-{m.away_score}
        </span>
        <span className="font-mono tabular-nums">{awayLabel}</span>
        {m.away.flag_url && (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={m.away.flag_url} alt="" className="w-3.5 h-2.5 rounded-[1px] object-cover" />
        )}
        <span className="text-rose-200/70 font-mono tabular-nums ml-1">{m.elapsed_min}&apos;</span>
        {data.live_count > 1 && (
          <span className="text-rose-200/70 ml-0.5">+{data.live_count - 1}</span>
        )}
        <span className="ml-1 text-rose-200/60 hidden sm:inline">Tap to watch</span>
      </Link>
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
