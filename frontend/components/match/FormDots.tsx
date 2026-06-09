import { Flag } from "@/components/common/Flag"
import type { Team } from "@/lib/types"

interface FormDotsProps {
  team: Team
  form: ("W" | "D" | "L")[]
}

const dotStyle = {
  W: "bg-green-900/40 text-green-400 border border-green-800/50",
  D: "bg-slate-800/60 text-slate-500 border border-slate-700",
  L: "bg-red-900/40 text-red-400 border border-red-800/50",
}

export function FormDots({ team, form }: FormDotsProps) {
  return (
    <div className="flex items-center gap-2">
      <div className="flex items-center gap-1.5 w-28">
        <Flag code={team.code} name={team.name} size="sm" />
        <span className="text-[11px] text-slate-500 truncate">{team.name}</span>
      </div>
      <div className="flex gap-1">
        {form.slice(-5).map((r, i) => (
          <span
            key={i}
            className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-bold ${dotStyle[r]}`}
          >
            {r}
          </span>
        ))}
      </div>
    </div>
  )
}
