import type { ScoreLine } from "@/lib/types"

interface ScoreGridProps {
  scores: ScoreLine[]
}

export function ScoreGrid({ scores }: ScoreGridProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {scores.map((s, i) => (
        <div key={i} className="bg-[#141929] border border-[#1a2033] rounded-md px-3 py-1.5 text-center min-w-[52px]">
          <p className="text-[13px] font-bold text-slate-200">{s.home}-{s.away}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">{Math.round(s.probability * 100)}%</p>
        </div>
      ))}
    </div>
  )
}
