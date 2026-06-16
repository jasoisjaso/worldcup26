"use client"
import { useState } from "react"
import type { TournamentProjection, TournamentTeam } from "@/lib/types"

type MetricKey = "p_advance" | "p_first" | "p_title"

interface MetricDef {
  key: MetricKey
  tab: string
  blurb: string
  tiers: { min: number; label: string }[]
}

const ADVANCE_TIERS = [
  { min: 0.85, label: "Through barring disaster" },
  { min: 0.55, label: "Should make it" },
  { min: 0.25, label: "On the bubble" },
  { min: 0, label: "Long shots" },
]
const GROUP_TIERS = [
  { min: 0.5, label: "Group favourites" },
  { min: 0.25, label: "In the mix" },
  { min: 0.08, label: "Outside chance" },
  { min: 0, label: "Unlikely" },
]
const TITLE_TIERS = [
  { min: 0.1, label: "Favourites" },
  { min: 0.04, label: "Contenders" },
  { min: 0.01, label: "Dark horses" },
  { min: 0, label: "Outsiders" },
]

function pct(n: number) {
  if (n >= 0.995) return "99%+"
  if (n > 0 && n < 0.005) return "<1%"
  return `${Math.round(n * 100)}%`
}

function Flag({ team }: { team: TournamentTeam }) {
  if (team.flag_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={team.flag_url} alt="" className="w-6 h-[18px] rounded-[2px] object-cover ring-1 ring-white/10 shrink-0" />
  }
  return (
    <span
      className="w-6 h-[18px] rounded-[2px] shrink-0 ring-1 ring-white/10"
      style={{ background: team.primary_color || "#1e293b" }}
    />
  )
}

function Row({ team, value, rank }: { team: TournamentTeam; value: number; rank: number }) {
  const w = Math.max(value * 100, value > 0 ? 1.5 : 0)
  const color = team.primary_color && team.primary_color !== "#ffffff" ? team.primary_color : "#10b981"
  return (
    <div className="group flex items-center gap-3 px-3 sm:px-4 py-2.5 rounded-xl hover:bg-white/[0.025] transition-colors">
      <span className="w-5 text-right font-mono text-[12px] tabular-nums text-slate-600 shrink-0">{rank}</span>
      <Flag team={team} />
      <div className="min-w-0 w-[112px] sm:w-[150px] shrink-0">
        <p className="text-[13px] font-semibold text-slate-100 truncate leading-tight">{team.name}</p>
        <p className="text-[10px] text-slate-500 leading-tight">
          Group {team.group} · {team.exp_points.toFixed(1)} pts
        </p>
      </div>
      <div className="flex-1 h-2.5 rounded-full bg-white/[0.04] overflow-hidden min-w-0">
        <div
          className="h-full rounded-full transition-all duration-500"
          style={{ width: `${w}%`, background: color, opacity: 0.85 }}
        />
      </div>
      <span className="font-mono text-[13px] tabular-nums font-bold text-slate-100 w-12 text-right shrink-0">
        {pct(value)}
      </span>
    </div>
  )
}

export function WinnerBoard({ data }: { data: TournamentProjection }) {
  const hasTitle = !!data.has_knockout && data.teams.some((t) => t.p_title != null)

  const metrics: MetricDef[] = [
    ...(hasTitle
      ? [{ key: "p_title" as MetricKey, tab: "Win it all", blurb: "Probability of lifting the trophy", tiers: TITLE_TIERS }]
      : []),
    { key: "p_advance", tab: "Reach knockouts", blurb: "Probability of finishing top two or as a qualifying best third", tiers: ADVANCE_TIERS },
    { key: "p_first", tab: "Win the group", blurb: "Probability of topping the group", tiers: GROUP_TIERS },
  ]

  const [metricKey, setMetricKey] = useState<MetricKey>(metrics[0].key)
  const metric = metrics.find((m) => m.key === metricKey) ?? metrics[0]

  const ranked = [...data.teams]
    .map((t) => ({ t, v: (t[metric.key] as number | undefined) ?? 0 }))
    .sort((a, b) => b.v - a.v)

  // group into tiers, dropping empty tiers
  const tiers = metric.tiers
    .map((tier, i) => {
      const upper = i === 0 ? 1.1 : metric.tiers[i - 1].min
      const members = ranked.filter(({ v }) => v >= tier.min && v < upper)
      return { label: tier.label, members }
    })
    .filter((tg) => tg.members.length > 0)

  let rank = 0

  return (
    <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">
      {/* hero */}
      <div className="mb-6">
        <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">The model's call</p>
        <h1 className="text-[26px] sm:text-[34px] font-black tracking-tight text-white leading-[1.05] mt-1">
          {hasTitle ? "Who wins the World Cup?" : "Who reaches the knockouts?"}
        </h1>
        <p className="text-[13px] text-slate-400 mt-2 max-w-xl">
          {data.n_sims.toLocaleString()} simulations of the remaining fixtures, sampling every match from
          the same Dixon-Coles model that powers the per-match pages. {metric.blurb}.
        </p>
      </div>

      {/* metric toggle */}
      <div className="flex gap-1.5 mb-4 p-1 rounded-xl bg-white/[0.03] w-fit">
        {metrics.map((m) => (
          <button
            key={m.key}
            onClick={() => setMetricKey(m.key)}
            aria-pressed={m.key === metricKey}
            className={[
              "px-3 py-1.5 rounded-lg text-[12px] font-semibold transition-colors",
              "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60",
              m.key === metricKey ? "bg-emerald-500 text-[#05130d]" : "text-slate-400 hover:text-slate-200",
            ].join(" ")}
          >
            {m.tab}
          </button>
        ))}
      </div>

      {/* tiered ladder */}
      <div className="rounded-2xl border border-[#16203200] bg-[#0a0f18]/60 divide-y divide-white/[0.04]">
        {tiers.map((tier) => (
          <div key={tier.label} className="py-2">
            <p className="px-4 pt-1.5 pb-1 text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">
              {tier.label}
            </p>
            {tier.members.map(({ t, v }) => {
              rank += 1
              return <Row key={t.code} team={t} value={v} rank={rank} />
            })}
          </div>
        ))}
      </div>

      <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
        Projections update as results come in and odds move.{" "}
        {data.completed_matches > 0
          ? `${data.completed_matches} group match${data.completed_matches === 1 ? "" : "es"} already factored in.`
          : "No group matches played yet — these are pre-tournament priors."}{" "}
        See how accurate the model has been on the{" "}
        <a href="/performance" className="text-emerald-400 hover:underline">report card</a>.
      </p>
    </div>
  )
}
