"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Flag } from "./Flag"
import type { Team } from "@/lib/types"

interface TeamMetaProps {
  team: Team
  align?: "left" | "right"
  /** When true, the team name + flag becomes a clickable link to /team/{code}.
   * Default true. Set false on the team detail page itself to avoid self-links. */
  linkable?: boolean
}

// Team flag + name + FIFA rank. By default the row is a Link to /team/{code}
// so users can drill into the team profile from anywhere a TeamMeta appears.
// `stopPropagation` is set so the click doesn't bubble to a parent Link (e.g.
// LiveMatchCard wraps the whole tile in a Link to /match/{id}).
export function TeamMeta({ team, align = "left", linkable = true }: TeamMetaProps) {
  const pathname = usePathname()
  const isRight = align === "right"
  const inner = (
    <>
      <Flag url={team.flag_url} name={team.name} size="lg" />
      <div className={`min-w-0 ${isRight ? "text-right" : ""}`}>
        <p className="text-[13px] sm:text-[15px] font-bold text-slate-100 truncate">{team.name}</p>
        <p className="text-[11px] text-slate-500 mt-0.5">
          {team.fifa_ranking ? `FIFA #${team.fifa_ranking}` : ""}
        </p>
      </div>
    </>
  )
  const cls = `flex items-center gap-2 min-w-0 ${isRight ? "flex-row-reverse" : ""}`
  if (linkable && team.code) {
    return (
      <Link
        href={`/team/${team.code}?from=${encodeURIComponent(pathname || "/")}`}
        onClick={(e) => e.stopPropagation()}
        className={`${cls} hover:opacity-80 transition-opacity`}
      >
        {inner}
      </Link>
    )
  }
  return <div className={cls}>{inner}</div>
}
