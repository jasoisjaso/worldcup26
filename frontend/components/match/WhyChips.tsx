import { TrendingUp, TrendingDown, Minus } from "lucide-react"
import type { WhyFactor } from "@/lib/types"

interface WhyChipsProps {
  factors: WhyFactor[]
}

const icons = {
  positive: TrendingUp,
  negative: TrendingDown,
  neutral: Minus,
}

const styles = {
  positive: "border-green-900 text-green-400 bg-green-950/40",
  negative: "border-red-900 text-red-400 bg-red-950/40",
  neutral: "border-slate-800 text-slate-400 bg-slate-900/40",
}

export function WhyChips({ factors }: WhyChipsProps) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {factors.map((f, i) => {
        const Icon = icons[f.direction]
        return (
          <span
            key={i}
            className={`inline-flex items-center gap-1.5 border rounded-md px-2 py-1 text-[11px] ${styles[f.direction]}`}
          >
            <Icon size={10} />
            {f.label}
          </span>
        )
      })}
    </div>
  )
}
