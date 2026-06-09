export function formatEV(ev: number): string {
  const sign = ev >= 0 ? "+" : ""
  return `${sign}${(ev * 100).toFixed(1)}% EV`
}

export function evColor(ev: number): string {
  if (ev > 0.05) return "text-green-400"
  if (ev > 0) return "text-green-300"
  if (ev < 0) return "text-red-400"
  return "text-slate-500"
}

export function evBorderColor(ev: number): string {
  if (ev > 0.05) return "border-l-green-500"
  if (ev > 0) return "border-l-green-700"
  return ""
}

export function formatOdds(odds: number): string {
  return odds.toFixed(2)
}

export function formatPercent(prob: number): string {
  return `${Math.round(prob * 100)}%`
}

export function kickoffLabel(isoString: string): string {
  const d = new Date(isoString)
  return d.toLocaleDateString("en-AU", {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}
