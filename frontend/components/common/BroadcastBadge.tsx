"use client"
import { useEffect, useState } from "react"

const DEFAULT_TZ = "Australia/Brisbane"
const TZ_KEY = "wc26_tz"

// SVG broadcaster chips styled to match real network brand identities
function SbsLogo() {
  return (
    <svg width="32" height="16" viewBox="0 0 32 16" fill="none" aria-label="SBS">
      <rect width="32" height="16" rx="3" fill="#E5001A" />
      <text x="16" y="11.5" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif"
        fontWeight="900" fontSize="9" letterSpacing="0.5" fill="white">SBS</text>
    </svg>
  )
}

function BbcLogo() {
  return (
    <svg width="38" height="16" viewBox="0 0 38 16" fill="none" aria-label="BBC">
      <rect width="12" height="16" rx="2" fill="black" />
      <rect x="13" width="12" height="16" rx="2" fill="black" />
      <rect x="26" width="12" height="16" rx="2" fill="black" />
      <text x="6" y="11.5" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif"
        fontWeight="900" fontSize="9" fill="white">B</text>
      <text x="19" y="11.5" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif"
        fontWeight="900" fontSize="9" fill="white">B</text>
      <text x="32" y="11.5" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif"
        fontWeight="900" fontSize="9" fill="white">C</text>
    </svg>
  )
}

function FoxLogo() {
  return (
    <svg width="32" height="16" viewBox="0 0 32 16" fill="none" aria-label="FOX">
      <rect width="32" height="16" rx="3" fill="#003087" />
      <text x="16" y="11.5" textAnchor="middle" fontFamily="Arial,Helvetica,sans-serif"
        fontWeight="900" fontSize="9" letterSpacing="0.5" fill="#FFD700">FOX</text>
    </svg>
  )
}

function getBroadcaster(tz: string): React.ReactNode | null {
  if (tz.startsWith("Australia/")) return <SbsLogo />
  if (tz === "Europe/London" || tz.startsWith("Europe/")) return <BbcLogo />
  if (tz.startsWith("America/")) return <FoxLogo />
  return null
}

export function BroadcastBadge() {
  const [tz, setTz] = useState<string | null>(null)

  useEffect(() => {
    const stored = localStorage.getItem(TZ_KEY) || DEFAULT_TZ
    setTz(stored)

    const handler = (e: Event) => {
      const newTz = (e as CustomEvent<{ tz: string }>).detail?.tz || DEFAULT_TZ
      setTz(newTz)
    }
    window.addEventListener("wc26_tz_change", handler)
    return () => window.removeEventListener("wc26_tz_change", handler)
  }, [])

  if (!tz) return null
  const badge = getBroadcaster(tz)
  if (!badge) return null

  return <span className="shrink-0 opacity-70 hover:opacity-100 transition-opacity">{badge}</span>
}
