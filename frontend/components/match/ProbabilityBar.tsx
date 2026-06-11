import { formatPercent } from "@/lib/utils"

interface ProbabilityBarProps {
  homeWin: number
  draw: number
  awayWin: number
  homeLabel: string
  awayLabel: string
}

export function ProbabilityBar({ homeWin, draw, awayWin, homeLabel, awayLabel }: ProbabilityBarProps) {
  return (
    <div className="mt-3">
      <div className="flex h-2 rounded-full overflow-hidden bg-[#131c2e]">
        <div className="bg-emerald-500 rounded-l-full" style={{ width: `${homeWin * 100}%` }} />
        <div className="bg-slate-600" style={{ width: `${draw * 100}%` }} />
        <div className="bg-orange-500 rounded-r-full" style={{ width: `${awayWin * 100}%` }} />
      </div>
      <div className="flex justify-between text-[10px] text-slate-600 mt-1">
        <span>{homeLabel}</span>
        <span className="text-slate-700">{formatPercent(draw)} draw</span>
        <span>{awayLabel}</span>
      </div>
    </div>
  )
}
