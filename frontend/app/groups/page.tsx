import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { GroupStanding } from "@/lib/types"
import Image from "next/image"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Group Tables",
  description: "Live 2026 FIFA World Cup group stage standings across all 12 groups.",
}

function FlagImg({ url, name }: { url?: string; name: string }) {
  if (!url) return <span className="w-5 h-3.5 bg-slate-700 rounded-sm inline-block" />
  return (
    <Image
      src={url}
      alt={name}
      width={20}
      height={14}
      className="rounded-sm object-cover"
      unoptimized
    />
  )
}

function GroupTable({ group, teams }: GroupStanding) {
  return (
    <div className="mb-5">
      <div className="flex items-center gap-2 px-1 mb-2">
        <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">
          Group {group}
        </span>
      </div>
      <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl overflow-hidden">
        {/* Header */}
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-3 px-3 py-2 border-b border-[#1a2033]">
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Team</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">P</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">W</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">D</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">L</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-7 text-center">GD</span>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest w-6 text-center">Pts</span>
        </div>
        {teams.map((t, i) => {
          const isQualified = i < 2 && t.played > 0
          const isEliminated = i >= 2 && t.played === 3
          return (
            <div
              key={t.code}
              className={[
                "grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto] gap-x-3 px-3 py-2.5 items-center border-b border-[#1a2033] last:border-b-0",
                i < 2 ? "border-l-2 border-l-green-700/60" : "border-l-2 border-l-transparent",
              ].join(" ")}
            >
              <div className="flex items-center gap-2 min-w-0">
                <FlagImg url={t.flag_url} name={t.name} />
                <span className={`text-[13px] font-semibold truncate ${isQualified ? "text-green-300" : isEliminated ? "text-slate-600" : "text-slate-200"}`}>
                  {t.name}
                </span>
              </div>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.played}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.won}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.drawn}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.lost}</span>
              <span className={`text-[12px] w-7 text-center font-medium ${t.gd > 0 ? "text-green-400" : t.gd < 0 ? "text-red-400" : "text-slate-500"}`}>
                {t.gd > 0 ? `+${t.gd}` : t.gd}
              </span>
              <span className="text-[13px] font-bold text-white w-6 text-center">{t.points}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default async function GroupsPage() {
  let groups: GroupStanding[] = []
  try {
    groups = await api.groups()
  } catch {
    groups = []
  }

  const played = groups.flatMap((g) => g.teams).some((t) => t.played > 0)

  return (
    <>
      <TopBar
        title="Group Standings"
        subtitle={played ? "Live standings — top 2 per group advance" : "Standings update as matches complete"}
      />
      <div className="px-4 py-4">
        {!played && (
          <div className="bg-[#0f1320] border border-[#1a2033] rounded-xl px-4 py-3 mb-5 text-[12px] text-slate-400">
            No matches played yet. Standings will update automatically as results come in.
            <span className="text-slate-300"> Top 2 from each group qualify automatically. The 8 best third-placed teams also advance — 32 of 48 teams progress.</span>
          </div>
        )}
        {groups.map((g) => (
          <GroupTable key={g.group} {...g} />
        ))}
      </div>
    </>
  )
}
