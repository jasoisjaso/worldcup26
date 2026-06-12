"use client"
import { useEffect, useState } from "react"

const DEFAULT_TZ = "Australia/Brisbane"
const TZ_KEY = "wc26_tz"

function toUtcDate(iso: string): Date {
  // Python isoformat() omits Z — browsers treat bare strings as local time, not UTC.
  // Force UTC by appending Z when there is no timezone info.
  const hasOffset = iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)
  return new Date(hasOffset ? iso : iso + "Z")
}

function fmt(iso: string, tz: string): string {
  return toUtcDate(iso).toLocaleString("en-AU", {
    timeZone: tz,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

export function KickoffTime({ iso }: { iso: string }) {
  // Start null so SSR emits nothing — avoids hydration mismatch from server/client TZ differences
  const [label, setLabel] = useState<string | null>(null)

  useEffect(() => {
    const tz = localStorage.getItem(TZ_KEY) || DEFAULT_TZ
    setLabel(fmt(iso, tz))

    const handler = (e: Event) => {
      const newTz = (e as CustomEvent<{ tz: string }>).detail?.tz || DEFAULT_TZ
      setLabel(fmt(iso, newTz))
    }
    window.addEventListener("wc26_tz_change", handler)
    return () => window.removeEventListener("wc26_tz_change", handler)
  }, [iso])

  return <span suppressHydrationWarning>{label ?? "—"}</span>
}
