"use client"
import { useEffect, useState } from "react"

interface Progress {
  stage: string
  total: number
  complete: number
  in_play: number
  remaining: number
  next_kickoff_iso: string | null
}

const TZ_KEY = "wc26_tz"
const DEFAULT_TZ = "Australia/Brisbane"

function toUtcDate(iso: string): Date {
  const hasOffset = iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)
  return new Date(hasOffset ? iso : iso + "Z")
}

function fmtCountdown(iso: string | null): string | null {
  if (!iso) return null
  const target = toUtcDate(iso).getTime()
  const now = Date.now()
  const diffMin = Math.floor((target - now) / 60000)
  if (diffMin < 0) return "now"
  if (diffMin < 60) return `in ${diffMin}m`
  const h = Math.floor(diffMin / 60)
  if (h < 24) return `in ${h}h`
  return `in ${Math.floor(h / 24)}d`
}

export function GroupStageProgress() {
  const [data, setData] = useState<Progress | null>(null)
  const [tz, setTz] = useState(DEFAULT_TZ)

  useEffect(() => {
    setTz(localStorage.getItem(TZ_KEY) || DEFAULT_TZ)
    let cancelled = false
    const fetchOnce = async () => {
      try {
        const r = await fetch("/api/proxy/progress").catch(() =>
          fetch("https://wc26.tinjak.com/api/tournament/progress", { cache: "no-store" })
        )
        if (cancelled) return
        const j = await r.json()
        setData(j)
      } catch { /* silent */ }
    }
    fetchOnce()
    const i = setInterval(fetchOnce, 60_000)  // refresh once a minute
    const onTz = (e: Event) => {
      const d = (e as CustomEvent).detail
      if (d?.tz) setTz(d.tz)
    }
    window.addEventListener("wc26_tz_change", onTz)
    return () => {
      cancelled = true
      clearInterval(i)
      window.removeEventListener("wc26_tz_change", onTz)
    }
  }, [])

  if (!data || !data.total) return null

  const completePct = Math.round((data.complete / data.total) * 100)
  const isAllDone = data.complete >= data.total

  const nextLabel = data.next_kickoff_iso
    ? toUtcDate(data.next_kickoff_iso).toLocaleString("en-AU", {
        timeZone: tz,
        weekday: "short",
        hour: "2-digit",
        minute: "2-digit",
      })
    : null

  const countdown = fmtCountdown(data.next_kickoff_iso)

  return (
    <div className="rounded-lg bg-surface-2 border border-edge px-2.5 py-1.5 flex items-center gap-2 min-w-0">
      {/* Progress bar — fixed-width on desktop, fluid on mobile */}
      <div className="flex flex-col gap-0.5 min-w-0 flex-1 sm:flex-none sm:w-[180px]">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[9.5px] font-bold uppercase tracking-widest text-slate-500 whitespace-nowrap">
            Group stage
          </span>
          <span className="text-[10px] font-mono text-slate-400 tabular-nums whitespace-nowrap">
            {data.complete}/{data.total}
            {data.in_play > 0 && <span className="ml-1 text-amber-400">·{data.in_play} live</span>}
          </span>
        </div>
        <div className="h-1 rounded-full bg-surface-0 overflow-hidden">
          <div
            className="h-full bg-emerald-500 transition-[width] duration-500"
            style={{ width: `${completePct}%` }}
          />
        </div>
      </div>

      {/* Next kickoff — hide on very small screens, show on sm+ */}
      {!isAllDone && nextLabel && countdown && (
        <div className="hidden sm:flex flex-col items-end shrink-0 border-l border-edge/40 pl-2.5">
          <span className="text-[9.5px] uppercase tracking-widest text-slate-600 whitespace-nowrap">
            Next kickoff
          </span>
          <span className="text-[10.5px] font-mono text-slate-300 whitespace-nowrap" suppressHydrationWarning>
            {countdown}
          </span>
        </div>
      )}
    </div>
  )
}
