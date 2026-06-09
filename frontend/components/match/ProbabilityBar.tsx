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
    <div className="mt-3.5">
      <div className="flex h-1.5 rounded-full overflow-hidden bg-slate-800 mb-1.5">
        <div className="bg-blue-600 rounded-l-full" style={{ width: `${homeWin * 100}%` }} />
        <div className="bg-slate-600" style={{ width: `${draw * 100}%` }} />
        <div className="bg-red-700 rounded-r-full" style={{ width: `${awayWin * 100}%` }} />
      </div>
      <div className="flex justify-between text-[11px]">
        <span className="font-bold text-blue-400">{formatPercent(homeWin)}</span>
        <span className="text-slate-500">{formatPercent(draw)} Draw</span>
        <span className="font-bold text-red-400">{formatPercent(awayWin)}</span>
      </div>
      <div className="flex justify-between text-[10px] text-slate-600 mt-0.5">
        <span>{homeLabel}</span>
        <span>{awayLabel}</span>
      </div>
    </div>
  )
}
