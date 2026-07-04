"use client"

import Link from "next/link"
import { useEffect, useState } from "react"

interface LiveTeam {
  code: string
  name: string
  flag_url?: string | null
  pts?: number
  gd?: number
  played?: number
}

interface LiveMatch {
  match: number
  id: string
  home_rule?: string
  away_rule?: string
  home: LiveTeam | null
  away: LiveTeam | null
  locked: boolean
  // Result block — present once the tie's Match row is seeded.
  seeded: boolean
  status: string | null
  home_score: number | null
  away_score: number | null
  so_home: number | null
  so_away: number | null
  kickoff: string | null
  winner: "home" | "away" | null
}

interface LiveRound {
  name: string
  matches: LiveMatch[]
}

interface LiveBracketData {
  groups_done: number
  total_groups: number
  third_qualifiers: string[]
  bracket: { rounds: LiveRound[] }
}

function ruleLabel(rule?: string): string {
  if (!rule) return "TBD"
  if (rule.startsWith("W")) return `Winner M${rule.slice(1)}`
  if (rule.startsWith("L")) return `Loser M${rule.slice(1)}`
  if (rule.startsWith("1")) return `Winners ${rule.slice(1)}`
  if (rule.startsWith("2")) return `Runners-up ${rule.slice(1)}`
  if (rule.startsWith("3")) return "3rd place"
  return rule
}

function kickoffLabel(iso: string | null): string {
  if (!iso) return ""
  const d = new Date(iso)
  return d.toLocaleString("en-AU", {
    timeZone: "Australia/Brisbane",
    weekday: "short", day: "numeric", month: "short",
    hour: "numeric", minute: "2-digit",
  })
}

function TeamRow({ team, rule, side, m }: {
  team: LiveTeam | null; rule?: string; side: "home" | "away"; m: LiveMatch
}) {
  const isWinner = m.winner === side
  const decided = m.winner !== null
  const score = side === "home" ? m.home_score : m.away_score
  const so = side === "home" ? m.so_home : m.so_away
  return (
    <div className={`flex items-center gap-1.5 px-2.5 py-1.5 ${isWinner ? "bg-emerald-500/[0.08]" : ""}`}>
      {team ? (
        <>
          {team.flag_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={team.flag_url} alt="" className="w-4 h-3 rounded-[2px] object-cover shrink-0" />
          )}
          <span className={`text-[11px] truncate flex-1 ${
            isWinner ? "text-white font-bold"
            : decided ? "text-slate-500"
            : "text-slate-200 font-medium"
          }`}>
            {team.name}
          </span>
          {score !== null && (
            <span className={`text-[11px] font-mono tabular-nums shrink-0 ${isWinner ? "text-emerald-300 font-bold" : "text-slate-400"}`}>
              {score}{so !== null ? ` (${so})` : ""}
            </span>
          )}
        </>
      ) : (
        <span className="text-[10px] text-slate-600 italic truncate flex-1">
          {ruleLabel(rule)}
        </span>
      )}
    </div>
  )
}

function TieCard({ m }: { m: LiveMatch }) {
  const isComplete = m.status === "complete"
  const isPens = m.so_home !== null || m.so_away !== null
  const body = (
    <div className="rounded-lg border border-edge bg-surface-2 overflow-hidden hover:border-slate-500/60 transition-colors">
      <div className="px-2 py-1 bg-surface-1 border-b border-edge/50 flex items-center gap-2">
        <p className="text-[9px] text-slate-600 font-mono">Match {m.match}</p>
        {isComplete ? (
          <span className="ml-auto text-[8px] font-bold uppercase tracking-wider text-slate-500">
            FT{isPens ? " · pens" : ""}
          </span>
        ) : m.seeded && m.kickoff ? (
          <span className="ml-auto text-[8px] text-slate-500 truncate">{kickoffLabel(m.kickoff)}</span>
        ) : null}
      </div>
      <div className="divide-y divide-edge/60">
        <TeamRow team={m.home} rule={m.home_rule} side="home" m={m} />
        <TeamRow team={m.away} rule={m.away_rule} side="away" m={m} />
      </div>
    </div>
  )
  // Only seeded ties have a match page to land on. Unseeded future ties are
  // static cards showing where each winner feeds.
  if (!m.seeded) return body
  return (
    <Link href={`/match/${m.id}`} className="block">
      {body}
    </Link>
  )
}

export function BracketLive({ data: initialData }: { data: LiveBracketData }) {
  const [view, setView] = useState<"bracket" | "groups">("bracket")
  // SSR provides the first paint; we then poll every 60s so fresh results
  // propagate without a manual reload.
  const [data, setData] = useState<LiveBracketData>(initialData)
  useEffect(() => {
    let cancelled = false
    async function refresh() {
      try {
        const res = await fetch("/api/tournament/bracket-live", { cache: "no-store" })
        if (!res.ok) return
        const next = (await res.json()) as LiveBracketData
        if (!cancelled) setData(next)
      } catch { /* silent */ }
    }
    const id = setInterval(refresh, 60_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const rounds = data.bracket?.rounds || []
  const decidedTotal = rounds.flatMap((r) => r.matches).filter((m) => m.status === "complete").length
  const seededTotal = rounds.flatMap((r) => r.matches).filter((m) => m.seeded).length

  return (
    <div>
      {/* Header */}
      <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 p-3.5 flex items-center gap-3">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400 shrink-0">
          Live bracket
        </span>
        <span className="text-[13px] text-white font-semibold">
          {decidedTotal} of 32 knockout ties decided
        </span>
        <span className="ml-auto text-[11px] text-slate-400">
          {seededTotal} fixtures set
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
        <div className="space-y-6">
          {rounds.map((round) => (
            <div key={round.name}>
              <div className="flex items-center gap-2 mb-2">
                <h2 className="text-[11px] font-bold uppercase tracking-[0.15em] text-slate-400">{round.name}</h2>
                <span className="text-[10px] text-slate-600 font-mono">
                  {round.matches.filter((m) => m.status === "complete").length}/{round.matches.length} played
                </span>
              </div>
              <div className={`grid gap-2 ${
                round.matches.length >= 8 ? "grid-cols-2 sm:grid-cols-4"
                : round.matches.length >= 4 ? "grid-cols-2 sm:grid-cols-4"
                : round.matches.length >= 2 ? "grid-cols-2"
                : "grid-cols-1 max-w-xs"
              }`}>
                {round.matches.map((m) => (
                  <TieCard key={m.match} m={m} />
                ))}
              </div>
            </div>
          ))}
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
    </div>
  )
}
