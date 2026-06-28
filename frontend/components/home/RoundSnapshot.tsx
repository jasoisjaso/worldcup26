import { Trophy, TrendingUp, Clock } from "lucide-react"
import { KickoffCountdown } from "@/components/common/KickoffCountdown"
import type { Match, MatchPrediction } from "@/lib/types"

/**
 * Slim stats banner for knockout rounds. Replaces the static "single
 * elimination" disclaimer with a live, useful round summary.
 *
 * Three slots:
 *   - countdown to next kickoff
 *   - matches remaining today / total
 *   - count of value picks the model is currently seeing
 */
export function RoundSnapshot({
  matches,
  roundLabel,
}: {
  matches: (Match & { prediction?: MatchPrediction })[]
  roundLabel: string
}) {
  const now = Date.now()
  const upcoming = matches.filter((m) => m.status === "upcoming")
  // "Next 24h" — more useful than a Brisbane calendar-day count, since the
  // knockout schedule clusters US kickoffs into AEST mornings. Calendar-day
  // semantics would often show "0 today" while another match is 14 hours away.
  const horizon = now + 24 * 60 * 60 * 1000
  const next24h = matches.filter((m) => {
    const ko = new Date(m.kickoff).getTime()
    return ko >= now && ko <= horizon
  }).length

  const nextKick = upcoming.length
    ? upcoming.sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())[0].kickoff
    : null

  const valueCount = matches.filter((m) =>
    m.prediction?.markets.some((mk) => mk.ev > 0.05),
  ).length

  return (
    <div className="mb-4 grid grid-cols-3 gap-2 sm:gap-3">
      <Stat
        icon={<Clock size={14} className="text-emerald-400" />}
        label="Next kick-off"
        value={
          nextKick ? (
            <KickoffCountdown iso={nextKick} />
          ) : (
            <span className="text-slate-400">Round complete</span>
          )
        }
      />
      <Stat
        icon={<Trophy size={14} className="text-amber-400" />}
        label="Next 24 hours"
        value={
          <span className="tabular-nums">
            {next24h}
            <span className="text-slate-500 text-[12px] font-normal"> / {matches.length} this round</span>
          </span>
        }
      />
      <Stat
        icon={<TrendingUp size={14} className="text-emerald-400" />}
        label={`Model edge`}
        value={
          <span className="tabular-nums">
            {valueCount}
            <span className="text-slate-500 text-[12px] font-normal"> with +5% value</span>
          </span>
        }
      />
    </div>
  )
}

function Stat({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: React.ReactNode
}) {
  return (
    <div className="rounded-xl border border-edge bg-surface-2/40 px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-[9px] sm:text-[10px] font-bold uppercase tracking-widest text-slate-500">
        {icon}
        {label}
      </p>
      <p className="text-[14px] sm:text-[16px] font-bold text-ink mt-1 leading-tight">{value}</p>
    </div>
  )
}
