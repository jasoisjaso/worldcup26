export function formatEV(ev: number): string {
  const sign = ev >= 0 ? "+" : ""
  return `${sign}${(ev * 100).toFixed(1)}% EV`
}

// Negative EV is amber, not red: red-vs-green is the exact pair red-green colour blindness
// cannot tell apart, and a betting audience skews heavily male (~8% affected). Amber-vs-emerald
// stays distinguishable, and evGlyph adds a redundant shape so meaning survives greyscale.
export function evColor(ev: number): string {
  if (ev > 0.05) return "text-emerald-400"
  if (ev > 0) return "text-emerald-300"
  if (ev < 0) return "text-amber-500"
  return "text-slate-500"
}

export function evGlyph(ev: number): string {
  return ev > 0 ? "▲" : ev < 0 ? "▼" : "·"
}

export function evBorderColor(ev: number): string {
  if (ev > 0.05) return "border-l-emerald-500"
  if (ev > 0) return "border-l-emerald-700"
  return ""
}

export function formatOdds(odds: number): string {
  return odds.toFixed(2)
}

export function formatPercent(prob: number): string {
  return `${Math.round(prob * 100)}%`
}

function toUtcDate(iso: string): Date {
  const hasOffset = iso.endsWith("Z") || /[+-]\d{2}:\d{2}$/.test(iso)
  return new Date(hasOffset ? iso : iso + "Z")
}

export function kickoffLabel(isoString: string, tz: string = "Australia/Brisbane"): string {
  return toUtcDate(isoString).toLocaleDateString("en-AU", {
    timeZone: tz,
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
