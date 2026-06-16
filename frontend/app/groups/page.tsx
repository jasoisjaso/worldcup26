import { TopBar } from "@/components/layout/TopBar"
import { GroupsInteractive } from "@/components/groups/GroupsInteractive"
import { api } from "@/lib/api"
import type { GroupStanding } from "@/lib/types"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Group Tables",
  description: "Live 2026 FIFA World Cup group stage standings across all 12 groups.",
}

export const dynamic = "force-dynamic"

export default async function GroupsPage() {
  let groups: GroupStanding[] = []
  const advance: Record<string, number> = {}
  try {
    const [g, proj] = await Promise.all([api.groups(), api.tournament().catch(() => null)])
    groups = g
    proj?.teams.forEach((t) => { advance[t.code] = t.p_advance })
  } catch {
    groups = []
  }

  const played = groups.flatMap((g) => g.teams).some((t) => t.played > 0)

  return (
    <>
      <TopBar
        title="Group Standings"
        subtitle={played ? "Live standings. Top 2 per group advance." : "Standings update as matches complete."}
      />
      <div className="px-4 py-4 max-w-4xl mx-auto">
        <GroupsInteractive groups={groups} advance={advance} noMatchesPlayed={!played} />
      </div>
    </>
  )
}
