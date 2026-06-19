import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "Group Scenarios: What Each Team Needs to Advance",
  description:
    "Every WC2026 group's matchday 3 outcomes. Who's through, who needs a win, who needs help, who's out, based on every possible result.",
  alternates: { canonical: "https://wc26.tinjak.com/scenarios" },
}

export const dynamic = "force-dynamic"

interface ScenarioTeam {
  code: string
  name: string
  played: number
  pts: number
  gd: number
  gf: number
  max_points: number
  min_position: number
  max_position: number
  advance_pct: number
  status: string
  detail: string
}

interface ScenarioFixture {
  match_id: string
  home_code: string
  home_name: string
  away_code: string
  away_name: string
  kickoff: string | null
}

interface ScenarioGroup {
  group: string
  matches_remaining: number
  remaining_fixtures: ScenarioFixture[]
  teams: ScenarioTeam[]
}

const STATUS_COLORS: Record<string, string> = {
  GUARANTEED: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  NEED_WIN: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  WIN_TO_WIN_GROUP: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  NEED_HELP: "text-orange-400 bg-orange-500/10 border-orange-500/20",
  IN_CONTENTION: "text-blue-400 bg-blue-500/10 border-blue-500/20",
  ELIMINATED: "text-slate-500 bg-slate-500/10 border-slate-500/20",
}

const STATUS_LABELS: Record<string, string> = {
  GUARANTEED: "THROUGH",
  NEED_WIN: "MUST WIN",
  WIN_TO_WIN_GROUP: "WIN = TOP",
  NEED_HELP: "NEEDS HELP",
  IN_CONTENTION: "ALIVE",
  ELIMINATED: "OUT",
}

export default async function ScenariosPage() {
  let groups: ScenarioGroup[] = []
  try {
    groups = (await api.scenarios()) ?? []
  } catch {
    groups = []
  }

  const active = groups.filter((g) => g.matches_remaining > 0)
  const done = groups.filter((g) => g.matches_remaining === 0)

  return (
    <>
      <TopBar title="Knockout scenarios" subtitle="What every team needs to reach the Round of 32" />
      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-4">
        {groups.length === 0 ? (
          <p className="text-slate-500 text-sm py-12 text-center">Scenarios warm up once the first match has been played.</p>
        ) : (
          <>
            {active.map((g) => (
              <div key={g.group} className="mb-5 rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
                <div className="px-4 py-3 border-b border-edge/70 flex items-center justify-between">
                  <p className="text-[14px] font-bold text-white">Group {g.group}</p>
                  <span className="text-[10px] text-slate-500">
                    {g.matches_remaining} match{g.matches_remaining > 1 ? "es" : ""} left
                  </span>
                </div>

                {g.remaining_fixtures.length > 0 && (
                  <div className="px-4 py-2 bg-surface-1 border-b border-edge/40">
                    <p className="text-[9px] uppercase tracking-wider text-slate-600 mb-1.5">Remaining</p>
                    {g.remaining_fixtures.map((f) => (
                      <div
                        key={f.match_id}
                        className="text-[11px] text-slate-400 flex items-center gap-1.5 py-0.5"
                      >
                        <span>{f.home_name}</span>
                        <span className="text-slate-600">vs</span>
                        <span>{f.away_name}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="divide-y divide-edge/50">
                  {g.teams.map((t) => (
                    <div key={t.code} className="px-4 py-3">
                      <div className="flex items-center gap-2.5">
                        <span className="text-[11px] font-mono tabular-nums text-slate-600 w-9 shrink-0">
                          {t.pts}pts
                        </span>
                        <span className="text-[13px] font-semibold text-white flex-1 truncate">{t.name}</span>
                        <span
                          className={`text-[9px] font-bold px-1.5 py-0.5 rounded border ${
                            STATUS_COLORS[t.status] || "text-slate-500 border-edge"
                          }`}
                        >
                          {STATUS_LABELS[t.status] || t.status}
                        </span>
                        <span className="text-[10px] font-mono tabular-nums text-slate-400 w-10 text-right shrink-0">
                          {t.advance_pct}%
                        </span>
                      </div>
                      <p className="text-[10.5px] text-slate-500 leading-snug mt-1 pl-[44px]">
                        {t.detail}
                        {t.min_position && t.max_position && (
                          <span className="text-slate-600 ml-1">
                            (finish {t.min_position}
                            {t.min_position !== t.max_position ? `-${t.max_position}` : ""})
                          </span>
                        )}
                      </p>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            {done.length > 0 && (
              <div className="mb-5 rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
                <div className="px-4 py-3 border-b border-edge/70">
                  <p className="text-[13px] font-bold text-slate-400">Groups completed</p>
                </div>
                <div className="px-4 py-2 flex flex-wrap gap-2">
                  {done.map((g) => (
                    <span
                      key={g.group}
                      className="text-[11px] px-2 py-1 rounded bg-surface-1 text-slate-500"
                    >
                      Group {g.group}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </>
        )}

        <p className="text-[11px] text-slate-500 leading-relaxed mt-4">
          Statuses come from running every possible win/loss/draw combination of the remaining matchday 3 games and
          checking whether each team finishes in the top 2 or as a qualifying third-placed side.
        </p>
      </div>
    </>
  )
}
