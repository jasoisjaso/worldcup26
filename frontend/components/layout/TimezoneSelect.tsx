"use client"
import { useEffect, useState } from "react"

const TZ_KEY = "wc26_tz"
const DEFAULT_TZ = "Australia/Brisbane"

const TIMEZONES = [
  { value: "Australia/Brisbane", label: "AEST Brisbane" },
  { value: "Australia/Sydney", label: "AEDT Sydney" },
  { value: "Australia/Perth", label: "AWST Perth" },
  { value: "Europe/London", label: "BST London" },
  { value: "America/New_York", label: "ET New York" },
  { value: "America/Los_Angeles", label: "PT Los Angeles" },
  { value: "Asia/Tokyo", label: "JST Tokyo" },
  { value: "UTC", label: "UTC" },
]

export function TimezoneSelect() {
  const [tz, setTz] = useState(DEFAULT_TZ)

  useEffect(() => {
    const stored = localStorage.getItem(TZ_KEY)
    if (stored) setTz(stored)
  }, [])

  const handleChange = (newTz: string) => {
    setTz(newTz)
    localStorage.setItem(TZ_KEY, newTz)
    window.dispatchEvent(new CustomEvent("wc26_tz_change", { detail: { tz: newTz } }))
  }

  return (
    <select
      value={tz}
      onChange={(e) => handleChange(e.target.value)}
      suppressHydrationWarning
      className="text-[10px] bg-[#0c1220] border border-[#1a2033] text-slate-400 rounded px-1.5 py-1 focus:outline-none cursor-pointer hover:border-[#252f45] transition-colors"
    >
      {TIMEZONES.map((t) => (
        <option key={t.value} value={t.value}>
          {t.label}
        </option>
      ))}
    </select>
  )
}
