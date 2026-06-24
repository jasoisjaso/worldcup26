"use client"
import { useEffect, useState } from "react"
import Image from "next/image"
import { TeamDrawer } from "@/components/team/TeamDrawer"
import type { GroupStanding } from "@/lib/types"

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

const RAIL = ["border-l-emerald-500/70", "border-l-emerald-500/70", "border-l-amber-400/80", "border-l-rose-700/70"]

function GroupTable({
  group,
  teams,
  advance,
  onTeamClick,
  highlighted,
}: GroupStanding & {
  advance: Record<string, number>
  onTeamClick: (code: string) => void
  highlighted: boolean
}) {
  return (
    <div id={`group-${group}`} className="mb-5 scroll-mt-20">
      <div className="flex items-center gap-2 px-1 mb-2">
        <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Group {group}</span>
      </div>
      <div className={[
        "bg-surface-2 border rounded-xl shadow-e1 overflow-hidden transition-colors",
        highlighted ? "border-emerald-600/50 ring-1 ring-emerald-500/30" : "border-edge",
      ].join(" ")}>
        <div className="grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_72px] gap-x-2.5 px-3 py-2 border-b border-edge">
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest">Team</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">P</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">W</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">D</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-5 text-center">L</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest w-7 text-center">GD</span>
          <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest w-6 text-center">Pts</span>
          <span className="text-[10px] font-bold text-slate-600 uppercase tracking-widest text-right">Advance</span>
        </div>
        {teams.map((t, i) => {
          const adv = advance[t.code]
          return (
            <div
              key={t.code}
              className={[
                "grid grid-cols-[1fr_auto_auto_auto_auto_auto_auto_72px] gap-x-2.5 px-3 py-2.5 items-center border-b border-edge last:border-b-0 border-l-2",
                RAIL[i] ?? "border-l-transparent",
                i === 2 ? "border-t border-dashed border-emerald-500/30" : "",
              ].join(" ")}
            >
              <div className="flex items-center gap-2 min-w-0">
                <FlagImg url={t.flag_url} name={t.name} />
                <button
                  onClick={() => onTeamClick(t.code)}
                  className="text-[13px] font-semibold truncate text-left text-slate-200 hover:text-white hover:underline underline-offset-2 transition-colors"
                >
                  {t.name}
                </button>
              </div>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.played}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.won}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.drawn}</span>
              <span className="text-[12px] text-slate-400 w-5 text-center">{t.lost}</span>
              <span className={`text-[12px] w-7 text-center font-medium tabular-nums ${t.gd > 0 ? "text-emerald-400" : t.gd < 0 ? "text-rose-400" : "text-slate-500"}`}>
                {t.gd > 0 ? `+${t.gd}` : t.gd}
              </span>
              <span className="text-[13px] font-bold text-white w-6 text-center tabular-nums">{t.points}</span>
              {adv != null ? (
                <div className="relative h-4 rounded bg-emerald-950/50 overflow-hidden" title={`${Math.round(adv * 100)}% to advance`}>
                  <div className="absolute inset-y-0 left-0 bg-emerald-500/70 rounded" style={{ width: `${Math.min(100, adv * 100)}%` }} />
                  <span className="absolute inset-0 flex items-center justify-center font-mono text-[9px] tabular-nums text-white">{Math.round(adv * 100)}%</span>
                </div>
              ) : <span />}
            </div>
          )
        })}
      </div>
    </div>
  )
}

interface Props {
  groups: GroupStanding[]
  advance: Record<string, number>
  noMatchesPlayed: boolean
}

function ZoneKey({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="w-2.5 h-2.5 rounded-sm" style={{ background: color }} />
      <span className="text-slate-400">{label}</span>
    </span>
  )
}

export function GroupsInteractive({ groups: initialGroups, advance, noMatchesPlayed }: Props) {
  const [selectedTeam, setSelectedTeam] = useState<string | null>(null)
  // Group deeplink. Match pages link to /groups?focus=C; we scroll the matching
  // table into view + highlight it for a few seconds so the user lands exactly
  // where they expected. Fades after 6s so it doesn't dominate the page.
  const [focusedGroup, setFocusedGroup] = useState<string | null>(null)
  // Live standings refresh. Polls /api/groups every 60s so points/GD update
  // without the user reloading. Direct response to: 'isnt updating with live
  // scores for most up to date recommendations'.
  const [groups, setGroups] = useState<GroupStanding[]>(initialGroups)
  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const res = await fetch("/api/groups", { cache: "no-store" })
        if (!res.ok) return
        const next = (await res.json()) as GroupStanding[]
        if (!cancelled) setGroups(next)
      } catch { /* silent */ }
    }
    const id = setInterval(refresh, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  useEffect(() => {
    const params = new URLSearchParams(window.location.search)
    const focus = params.get("focus")
    if (!focus) return
    setFocusedGroup(focus)
    const el = document.getElementById(`group-${focus}`)
    if (el) el.scrollIntoView({ behavior: "smooth", block: "start" })
    const t = setTimeout(() => setFocusedGroup(null), 6000)
    return () => clearTimeout(t)
  }, [])

  return (
    <>
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[11px] mb-4 px-1">
        <ZoneKey color="#10b981" label="Top 2 advance" />
        <ZoneKey color="#fbbf24" label="3rd: best-third race" />
        <ZoneKey color="#b91c1c" label="4th: out" />
        <span className="text-slate-600">Bar = model chance to advance</span>
      </div>
      {noMatchesPlayed && (
        <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3 mb-5 text-[12px] text-slate-400">
          No matches played yet. Standings update as results come in.
          <span className="text-slate-300"> Top 2 from each group qualify. The 8 best third-placed teams also advance. 32 of 48 teams progress.</span>
        </div>
      )}
      {groups.map((g) => (
        <GroupTable
          key={g.group}
          {...g}
          advance={advance}
          onTeamClick={setSelectedTeam}
          highlighted={focusedGroup === g.group}
        />
      ))}
      {selectedTeam && (
        <TeamDrawer code={selectedTeam} onClose={() => setSelectedTeam(null)} />
      )}
    </>
  )
}
