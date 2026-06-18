"use client"

import { useState } from "react"

interface LiveTeam {
  code: string
  name: string
  pts: number
  gd: number
  played: number
}

interface LiveMatch {
  match: number
  home_rule?: string
  away_rule?: string
  home: LiveTeam | null
  away: LiveTeam | null
  locked: boolean
}

interface LiveRound {
  name: string
  matches: LiveMatch[]
  tbd?: boolean
}

interface LiveBracketData {
  groups_done: number
  total_groups: number
  third_qualifiers: string[]
  bracket: { rounds: LiveRound[] }
}

function ruleLabel(rule?: string): string {
  if (!rule) return ""
  if (rule.startsWith("1")) return `Winners ${rule.slice(1)}`
  if (rule.startsWith("2")) return `Runners-up ${rule.slice(1)}`
  if (rule.startsWith("3")) return "3rd place"
  return rule
}

function TeamSlot({ team, rule, locked }: { team: LiveTeam | null; rule?: string; locked: boolean }) {
  return (
    <div
      className={`flex items-center gap-1.5 px-2.5 py-1.5 ${
        locked
          ? "bg-emerald-500/10 border border-emerald-500/30 rounded"
          : "bg-white/[0.02]"
      }`}
    >
      {team ? (
        <>
          <span className={`text-[11px] font-semibold truncate flex-1 ${locked ? "text-white" : "text-slate-400"}`}>
            {team.name}
          </span>
          {locked && <span className="text-emerald-400 text-[9px] font-mono shrink-0">LOCKED</span>}
        </>
      ) : (
        <span className="text-[10px] text-slate-600 italic truncate flex-1">
          {rule ? ruleLabel(rule) : "TBD"}
        </span>
      )}
    </div>
  )
}

export function BracketLive({ data }: { data: LiveBracketData }) {
  const [view, setView] = useState<"bracket" | "groups">("bracket")

  const r32 = data.bracket?.rounds?.[0]?.matches || []
  const lockedCount = r32.filter((m) => m.locked).length

  return (
    <div>
      {/* Header */}
      <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 flex items-center gap-3">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400 shrink-0">
          Live bracket
        </span>
        <span className="text-[13px] text-white font-semibold">
          {data.groups_done}/{data.total_groups} groups complete
        </span>
        <span className="ml-auto text-[11px] text-slate-400">
          {lockedCount}/16 R32 slots locked
        </span>
      </div>

      {/* Tab toggle */}
      <div className="flex gap-1 mb-4">
        <button
          onClick={() => setView("bracket")}
          className={`text-[11px] font-bold px-3 py-1.5 rounded-lg transition-colors ${
            view === "bracket" ? "bg-emerald-500 text-white" : "bg-surface-2 text-slate-400 hover:text-white"
          }`}
        >
          Bracket
        </button>
        <button
          onClick={() => setView("groups")}
          className={`text-[11px] font-bold px-3 py-1.5 rounded-lg transition-colors ${
            view === "groups" ? "bg-emerald-500 text-white" : "bg-surface-2 text-slate-400 hover:text-white"
          }`}
        >
          Group results
        </button>
      </div>

      {view === "bracket" ? (
        /* R32 bracket grid */
        <div className="overflow-x-auto pb-3">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 min-w-[600px]">
            {r32.map((m) => (
              <div key={m.match} className="rounded-lg border border-edge bg-surface-2 overflow-hidden">
                <div className="px-2 py-1 bg-surface-1 border-b border-edge/50">
                  <p className="text-[9px] text-slate-600 font-mono">Match {m.match}</p>
                </div>
                <div className="divide-y divide-edge/60">
                  <TeamSlot team={m.home} rule={m.home_rule} locked={m.locked} />
                  <TeamSlot team={m.away} rule={m.away_rule} locked={m.locked} />
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : (
        /* Group results summary */
        <div className="rounded-xl border border-edge bg-surface-2 overflow-hidden">
          <div className="px-4 py-2 bg-surface-1 border-b border-edge/70">
            <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">
              Group stage results
            </p>
          </div>
          <div className="p-3 grid sm:grid-cols-2 gap-3">
            {Object.entries((data as any).groups || {}).map(([g, gdata]: [string, any]) => (
              <div key={g} className="rounded-lg border border-edge/50 p-2.5">
                <div className="flex items-center justify-between mb-1.5">
                  <p className="text-[11px] font-bold text-white">Group {g}</p>
                  {gdata.done ? (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 font-bold">DONE</span>
                  ) : (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400">IN PROGRESS</span>
                  )}
                </div>
                {gdata.teams?.map((t: any, i: number) => (
                  <div key={t.code} className="flex items-center gap-2 text-[10px] py-0.5">
                    <span className="text-slate-600 font-mono w-4">{i + 1}.</span>
                    <span className={`flex-1 truncate ${i < 2 ? "text-slate-100 font-medium" : "text-slate-500"}`}>
                      {t.name}
                    </span>
                    <span className="text-slate-600 tabular-nums">{t.pts}pts</span>
                    {t.gd !== undefined && (
                      <span className={`text-[9px] tabular-nums w-8 text-right ${t.gd > 0 ? "text-emerald-400" : t.gd < 0 ? "text-rose-400" : "text-slate-600"}`}>
                        {t.gd > 0 ? "+" : ""}{t.gd}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Progress bar */}
      <div className="mt-4">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-[10px] text-slate-500">Groups complete</span>
          <span className="text-[10px] font-mono text-slate-300">{data.groups_done}/12</span>
        </div>
        <div className="h-1 rounded-full bg-surface-1 overflow-hidden">
          <div
            className="h-full rounded-full bg-emerald-500 transition-all"
            style={{ width: `${(data.groups_done / 12) * 100}%` }}
          />
        </div>
      </div>
    </div>
  )
}
