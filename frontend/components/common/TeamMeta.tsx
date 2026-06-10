import { Flag } from "./Flag"
import type { Team } from "@/lib/types"

interface TeamMetaProps {
  team: Team
  align?: "left" | "right"
}

export function TeamMeta({ team, align = "left" }: TeamMetaProps) {
  const isRight = align === "right"
  return (
    <div className={`flex items-center gap-2 min-w-0 ${isRight ? "flex-row-reverse" : ""}`}>
      <Flag url={team.flag_url} name={team.name} size="lg" />
      <div className={`min-w-0 ${isRight ? "text-right" : ""}`}>
        <p className="text-[13px] sm:text-[15px] font-bold text-slate-100 truncate">{team.name}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {team.fifa_ranking ? `FIFA #${team.fifa_ranking}` : ""}
        </p>
      </div>
    </div>
  )
}
