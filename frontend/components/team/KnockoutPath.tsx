import Link from "next/link"
import { ChevronRight, Trophy } from "lucide-react"
import { api } from "@/lib/api"
import type { TournamentTeam, LikelyOpponent, LikelyPathStep } from "@/lib/types"

const ROUND_LABEL: Record<LikelyPathStep["round"], string> = {
  r32: "Round of 32",
  r16: "Round of 16",
  qf:  "Quarter-final",
  sf:  "Semi-final",
  final: "Final",
}

const ROUND_SHORT: Record<LikelyPathStep["round"], string> = {
  r32: "R32",
  r16: "R16",
  qf:  "QF",
  sf:  "SF",
  final: "Final",
}

const ROUND_KEYS: LikelyPathStep["round"][] = ["r32", "r16", "qf", "sf", "final"]

function fmtPct(p: number | undefined): string {
  if (p == null) return "—"
  if (p < 0.005) return "<1%"
  return `${Math.round(p * 100)}%`
}

export async function KnockoutPath({ code, teamName }: { code: string; teamName: string }) {
  let team: TournamentTeam | undefined
  try {
    const proj = await api.tournament()
    team = proj.teams?.find((t) => t.code === code)
  } catch {
    return null
  }

  if (!team || !team.likely_opponents) return null
  const path = team.likely_path ?? []
  const opponents = team.likely_opponents

  // Per-round reach probability for the header chips. These come from the
  // sim's already-existing p_r16 / p_quarter / etc. so they don't double-count.
  const REACH: Record<LikelyPathStep["round"], number | undefined> = {
    r32: team.p_advance,   // p_advance = P(team reaches R32) since R32 = first knockout round
    r16: team.p_r16,
    qf:  team.p_quarter,
    sf:  team.p_semi,
    final: team.p_final,
  }

  // Hide the panel entirely if the team has essentially no path (e.g. already
  // mathematically out of contention).
  const survives = (team.p_advance ?? 0) > 0.02
  if (!survives) return null

  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 mb-5 overflow-hidden">
      <header className="px-5 pt-4 pb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Trophy size={14} className="text-amber-400" />
          <h2 className="text-[12px] font-bold uppercase tracking-widest text-slate-300">
            {teamName}&apos;s knockout path
          </h2>
        </div>
        <span className="text-[10px] font-mono text-slate-600">
          across 20k sims
        </span>
      </header>

      {/* Likely path row — most probable opponent in each round, falls off when
          the team is unlikely to be there. */}
      <div className="px-5 pb-3">
        <div className="flex items-stretch gap-1 overflow-x-auto pb-1">
          {ROUND_KEYS.map((rnd, i) => {
            const step = path.find((s) => s.round === rnd)
            const reach = REACH[rnd]
            const out = !step
            return (
              <div key={rnd} className="flex items-center shrink-0">
                <PathStep
                  round={rnd}
                  step={step}
                  reachProb={reach}
                  dim={out}
                />
                {i < ROUND_KEYS.length - 1 && (
                  <ChevronRight size={12} className="text-slate-700 mx-0.5 shrink-0" />
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* Per-round opponent alternatives */}
      <div className="border-t border-edge/60 divide-y divide-edge/40">
        {ROUND_KEYS.map((rnd) => {
          const opps = opponents[rnd] ?? []
          if (opps.length === 0) return null
          return <RoundDetail key={rnd} round={rnd} opponents={opps} />
        })}
      </div>
    </section>
  )
}

function PathStep({
  round,
  step,
  reachProb,
  dim,
}: {
  round: LikelyPathStep["round"]
  step: LikelyPathStep | undefined
  reachProb: number | undefined
  dim: boolean
}) {
  return (
    <div
      className={[
        "rounded-lg border px-2.5 py-1.5 min-w-[100px]",
        dim
          ? "border-slate-800 bg-slate-900/30 text-slate-600"
          : "border-edge bg-surface-3 text-slate-200",
      ].join(" ")}
    >
      <p className="text-[9px] uppercase tracking-wider opacity-70">
        {ROUND_SHORT[round]}{" "}
        <span className="font-mono">{fmtPct(reachProb)}</span>
      </p>
      <p className="text-[12px] font-semibold leading-snug">
        {step ? (
          <Link
            href={`/team/${step.code}`}
            className="hover:text-emerald-300"
          >
            vs {step.name}
          </Link>
        ) : (
          "(eliminated)"
        )}
      </p>
      {step && (
        <p className="text-[10px] text-slate-500 font-mono">
          {fmtPct(step.p)} of paths
        </p>
      )}
    </div>
  )
}

function RoundDetail({
  round,
  opponents,
}: {
  round: LikelyPathStep["round"]
  opponents: LikelyOpponent[]
}) {
  return (
    <div className="px-5 py-2">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">
        {ROUND_LABEL[round]}
      </p>
      <ul className="flex flex-wrap gap-1.5">
        {opponents.slice(0, 5).map((o) => (
          <li key={o.code}>
            <Link
              href={`/team/${o.code}`}
              className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md border border-edge bg-surface-3 text-[11.5px] text-slate-300 hover:bg-emerald-500/10 hover:border-emerald-500/30 hover:text-emerald-200 transition-colors"
            >
              {o.name}
              <span className="text-slate-500 font-mono">{fmtPct(o.p)}</span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  )
}
