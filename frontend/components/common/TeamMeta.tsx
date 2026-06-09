import { Flag } from "./Flag"
import type { Team } from "@/lib/types"

interface TeamMetaProps {
  team: Team
  align?: "left" | "right"
}

export function TeamMeta({ team, align = "left" }: TeamMetaProps) {
  const isRight = align === "right"
  return (
    <div className={`flex items-center gap-3 ${isRight ? "flex-row-reverse" : ""}`}>
      <Flag code={team.code} name={team.name} size="lg" />
      <div className={isRight ? "text-right" : ""}>
        <p className="text-[15px] font-bold text-slate-100">{team.name}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {team.fifa_ranking ? `FIFA #${team.fifa_ranking}` : ""}
          {team.elo ? ` · Rating ${Math.round(team.elo)}` : ""}
        </p>
      </div>
    </div>
  )
}
