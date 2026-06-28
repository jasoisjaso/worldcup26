"use client"
import { useEffect, useState } from "react"

/**
 * Live kickoff countdown. Server renders the initial "in 11h 47m" string; on
 * hydration the client ticks every second.
 *
 * Returns nothing once kickoff has passed (so it doesn't get stuck at "0s").
 * The parent should branch to "LIVE" / "FT" UI based on match.status.
 */
function format(ms: number): string {
  if (ms <= 0) return "kicked off"
  const sec = Math.floor(ms / 1000)
  const d = Math.floor(sec / 86400)
  const h = Math.floor((sec % 86400) / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (d > 0) return `in ${d}d ${h}h`
  if (h > 0) return `in ${h}h ${m}m`
  if (m > 0) return `in ${m}m ${s}s`
  return `in ${s}s`
}

export function KickoffCountdown({ iso, prefix = "" }: { iso: string; prefix?: string }) {
  const target = new Date(iso).getTime()
  const [delta, setDelta] = useState(() => target - Date.now())

  useEffect(() => {
    const id = setInterval(() => setDelta(target - Date.now()), 1000)
    return () => clearInterval(id)
  }, [target])

  if (delta <= 0) return null
  return (
    <span className="tabular-nums">
      {prefix}
      {format(delta)}
    </span>
  )
}
