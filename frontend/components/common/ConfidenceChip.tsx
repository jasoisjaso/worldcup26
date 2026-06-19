/**
 * ConfidenceChip — a Low / Med / High pill that summarises how concentrated
 * the model's outlook is. Single colour cue, no methodology disclosed.
 *
 * Bucketing rule (concentration of the 1X2 distribution):
 *   max(p_home, p_draw, p_away) >= 0.55  -> HIGH  (one outcome clearly favoured)
 *   max in [0.42, 0.55)                  -> MED   (favourite tilt, not nailed on)
 *   max <  0.42                          -> LOW   (genuinely open match)
 *
 * Compact variant (compact=true) is intended for list rows / match cards.
 * Default variant is intended for the verdict header.
 */
export type ConfidenceLevel = "high" | "med" | "low"

export function confidenceFromProbs(p_home: number, p_draw: number, p_away: number): ConfidenceLevel {
  const peak = Math.max(p_home, p_draw, p_away)
  if (peak >= 0.55) return "high"
  if (peak >= 0.42) return "med"
  return "low"
}

const META: Record<ConfidenceLevel, { label: string; dot: string; ring: string; text: string }> = {
  high: {
    label: "High confidence",
    dot: "bg-emerald-400",
    ring: "ring-emerald-400/30 bg-emerald-500/[0.06]",
    text: "text-emerald-300",
  },
  med: {
    label: "Medium confidence",
    dot: "bg-amber-400",
    ring: "ring-amber-400/30 bg-amber-500/[0.06]",
    text: "text-amber-300",
  },
  low: {
    label: "Wide-open match",
    dot: "bg-slate-400",
    ring: "ring-slate-400/30 bg-slate-500/[0.06]",
    text: "text-slate-300",
  },
}

export function ConfidenceChip({
  level,
  compact = false,
  className = "",
}: {
  level: ConfidenceLevel
  compact?: boolean
  className?: string
}) {
  const m = META[level]
  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full ring-1 text-[9px] uppercase tracking-wider font-bold ${m.ring} ${m.text} ${className}`}
        title={m.label}
      >
        <span className={`w-1 h-1 rounded-full ${m.dot}`} />
        {level === "low" ? "Open" : level === "med" ? "Med" : "High"}
      </span>
    )
  }
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-full ring-1 text-[10px] uppercase tracking-wider font-bold ${m.ring} ${m.text} ${className}`}
      title={m.label}
    >
      <span className={`w-1.5 h-1.5 rounded-full ${m.dot}`} />
      {m.label}
    </span>
  )
}
