"use client"
/**
 * Forecaster Scoreboard — us vs the market vs Opta on the same data.
 *
 * Per-match table: we and the market consensus only. Opta doesn't publish
 * per-match 1X2 probabilities so they don't fit here; the tournament-level
 * comparison below covers them.
 *
 * Tournament-level: every WC2026 team, side-by-side title / advance / first
 * probabilities vs Opta's pre-tournament forecast. Highlights the biggest
 * disagreements at top, then the full 48-team table.
 */
import { useMemo, useState } from "react"

interface ForecasterRow {
  forecaster: string
  label: string
  n_settled: number
  n_covered: number
  hit_rate: number | null
  brier: number | null
  log_loss: number | null
}

interface TournamentRow {
  code: string
  name: string
  flag_url?: string
  us: { p_title?: number; p_advance?: number; p_first?: number; p_r16?: number; p_quarter?: number }
  opta: { p_title?: number; p_advance?: number; p_first?: number; p_r16?: number; p_quarter?: number }
  title_delta: number
  advance_delta: number
}

interface MatchData {
  n_total_settled: number
  n_common_settled?: number
  forecasters: ForecasterRow[]
}

interface TournamentData {
  n_teams: number
  opta_source: string | null
  opta_captured: string | null
  teams: TournamentRow[]
}

function pct(p: number | undefined | null): string {
  if (p == null) return "—"
  if (p < 0.005 && p > 0) return "<1%"
  if (p > 0.995) return "99%+"
  return `${Math.round(p * 100)}%`
}

function fmt(n: number | null | undefined, dp = 3): string {
  return n == null ? "—" : n.toFixed(dp)
}

function deltaPill(delta: number) {
  if (Math.abs(delta) < 0.005) return <span className="text-slate-600 font-mono text-[10px]">~</span>
  const sign = delta > 0 ? "+" : "−"
  const abs = Math.abs(Math.round(delta * 1000) / 10)
  const color = delta > 0 ? "text-emerald-400" : "text-amber-400"
  return <span className={`font-mono text-[10px] ${color}`}>{sign}{abs}</span>
}

function MatchLevelTable({ data }: { data: MatchData }) {
  if (data.n_total_settled === 0) {
    return (
      <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
        <p className="text-[12px] text-slate-500">
          Match-level scoring starts as the group stage results land. Right now there are no settled matches in the comparison window.
        </p>
      </div>
    )
  }

  // Filter out forecasters that don't actually have per-match data (Opta).
  const scored = data.forecasters.filter((f) => f.brier != null)
  const us = scored.find((f) => f.forecaster === "model_blend")
  const winner = scored[0]
  const usIsWinning = us && winner && us.forecaster === winner.forecaster

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 flex items-center justify-between border-b border-edge/60">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/90">
          Per-match · vs the market consensus
        </p>
        <span className="text-[10px] text-slate-600 font-mono">
          {data.n_common_settled != null
            ? `${data.n_common_settled} scored side-by-side`
            : `${data.n_total_settled} matches settled`}
        </span>
      </div>
      <table className="w-full text-[12px]">
        <thead>
          <tr className="text-slate-600 text-[10px] uppercase tracking-wider">
            <th className="text-left px-4 py-2 font-semibold">#</th>
            <th className="text-left px-1 py-2 font-semibold">Forecaster</th>
            <th className="text-right px-2 py-2 font-semibold">Hit rate</th>
            <th className="text-right px-2 py-2 font-semibold">Brier</th>
            <th className="text-right px-4 py-2 font-semibold hidden sm:table-cell">Log loss</th>
          </tr>
        </thead>
        <tbody>
          {scored.map((f, i) => {
            const isUs = f.forecaster === "model_blend"
            const isLeader = i === 0
            return (
              <tr
                key={f.forecaster}
                className={`border-t border-edge/30 ${isUs ? "bg-emerald-500/5" : ""}`}
              >
                <td className="px-4 py-2.5">
                  <span className={`font-mono ${isLeader ? "text-amber-400" : "text-slate-600"}`}>
                    {isLeader ? "★" : i + 1}
                  </span>
                </td>
                <td className="px-1 py-2.5">
                  <span className={`font-semibold ${isUs ? "text-emerald-300" : "text-slate-200"}`}>
                    {f.label}
                  </span>
                  {f.n_covered > 0 && f.n_settled < f.n_covered && (
                    <span className="text-[9px] text-slate-600 ml-1">({f.n_settled}/{f.n_covered} covered)</span>
                  )}
                </td>
                <td className="text-right font-mono tabular-nums px-2 py-2.5 text-slate-100">
                  {f.hit_rate == null ? "—" : `${Math.round(f.hit_rate * 100)}%`}
                </td>
                <td className="text-right font-mono tabular-nums px-2 py-2.5 text-slate-100">
                  {fmt(f.brier)}
                </td>
                <td className="text-right font-mono tabular-nums px-4 py-2.5 text-slate-100 hidden sm:table-cell">
                  {fmt(f.log_loss)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
      <div className="px-4 py-3 border-t border-edge/40">
        <p className="text-[10px] text-slate-500 leading-relaxed">
          Lower Brier = sharper forecast. Hit rate = how often the favourite outcome won. The market consensus is the closing line averaged across every bookmaker we track and Shin-devigged. Every settled match is scored the same way for everybody. No cherry-picking.
          {usIsWinning && (
            <span className="ml-1 text-emerald-400 font-semibold">We&apos;re ahead of the market right now.</span>
          )}
        </p>
        <p className="text-[10px] text-slate-600 mt-2 leading-relaxed">
          The Opta supercomputer doesn&apos;t publish per-match win probabilities, only tournament-level outlooks. The head-to-head with Opta is below.
        </p>
      </div>
    </div>
  )
}

type SortKey = "title_disagree" | "advance_disagree" | "title_us" | "title_opta" | "name"

function TournamentLevelTable({ data }: { data: TournamentData }) {
  const [showAll, setShowAll] = useState(false)
  const [sort, setSort] = useState<SortKey>("title_disagree")

  if (data.n_teams === 0) return null

  const sorted = useMemo(() => {
    const arr = [...data.teams]
    if (sort === "title_disagree") arr.sort((a, b) => Math.abs(b.title_delta) - Math.abs(a.title_delta))
    else if (sort === "advance_disagree") arr.sort((a, b) => Math.abs(b.advance_delta) - Math.abs(a.advance_delta))
    else if (sort === "title_us") arr.sort((a, b) => (b.us.p_title || 0) - (a.us.p_title || 0))
    else if (sort === "title_opta") arr.sort((a, b) => (b.opta.p_title || 0) - (a.opta.p_title || 0))
    else if (sort === "name") arr.sort((a, b) => a.name.localeCompare(b.name))
    return arr
  }, [data.teams, sort])

  const bullish = useMemo(() => {
    return [...data.teams]
      .filter((t) => t.title_delta > 0)
      .sort((a, b) => b.title_delta - a.title_delta)
      .slice(0, 4)
  }, [data.teams])

  const cautious = useMemo(() => {
    return [...data.teams]
      .filter((t) => t.title_delta < 0)
      .sort((a, b) => a.title_delta - b.title_delta)
      .slice(0, 4)
  }, [data.teams])

  const aligned = useMemo(() => {
    // Teams where we and Opta agree closely AND both rate them seriously (top title odds).
    return [...data.teams]
      .filter((t) => (t.us.p_title || 0) >= 0.02 && (t.opta.p_title || 0) >= 0.02)
      .map((t) => ({ ...t, _abs: Math.abs(t.title_delta) }))
      .sort((a, b) => a._abs - b._abs)
      .slice(0, 3)
  }, [data.teams])

  const visible = showAll ? sorted : sorted.slice(0, 10)

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 flex items-center justify-between border-b border-edge/60">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/90">
          Tournament · vs the Opta supercomputer
        </p>
        <span className="text-[10px] text-slate-600 font-mono">{data.n_teams} teams</span>
      </div>

      {/* Disagreement panels — the shareable takes */}
      <div className="grid sm:grid-cols-2 gap-3 p-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-400/80 mb-1.5 px-1">
            We&apos;re more bullish on
          </p>
          <div className="space-y-1">
            {bullish.map((t) => <DeltaRow key={t.code} t={t} sign="+" />)}
            {bullish.length === 0 && (
              <p className="text-[11px] text-slate-600 px-1">No major disagreements where we&apos;re more bullish.</p>
            )}
          </div>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-400/80 mb-1.5 px-1">
            We&apos;re more cautious on
          </p>
          <div className="space-y-1">
            {cautious.map((t) => <DeltaRow key={t.code} t={t} sign="-" />)}
            {cautious.length === 0 && (
              <p className="text-[11px] text-slate-600 px-1">No major disagreements where we&apos;re more cautious.</p>
            )}
          </div>
        </div>
      </div>

      {/* Agreement panel — credibility cue */}
      {aligned.length > 0 && (
        <div className="px-3 pb-3">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 mb-1.5 px-1">
            Where we agree
          </p>
          <div className="rounded-lg bg-surface-1/50 border border-edge/40 px-2 py-2">
            <div className="flex flex-wrap gap-x-3 gap-y-1.5">
              {aligned.map((t) => (
                <div key={t.code} className="flex items-center gap-1.5">
                  {t.flag_url && (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={t.flag_url} alt="" className="w-4 h-3 rounded-[2px] ring-1 ring-white/10 shrink-0 object-cover" />
                  )}
                  <span className="text-[11px] text-slate-200">{t.name}</span>
                  <span className="text-[10px] text-slate-600 font-mono">
                    us {pct(t.us.p_title)} · opta {pct(t.opta.p_title)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* Full 48-team table — collapsible */}
      <div className="border-t border-edge/40">
        <div className="px-3 pt-3 pb-2 flex items-center justify-between gap-2">
          <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">
            Full table · title, advance, group winner
          </p>
          <select
            value={sort}
            onChange={(e) => setSort(e.target.value as SortKey)}
            className="text-[10px] bg-surface-1 border border-edge rounded px-2 py-1 text-slate-300 focus:outline-none focus:ring-1 focus:ring-emerald-500"
            aria-label="Sort table"
          >
            <option value="title_disagree">Most disagreement on title</option>
            <option value="advance_disagree">Most disagreement on advance</option>
            <option value="title_us">Our title %</option>
            <option value="title_opta">Opta&apos;s title %</option>
            <option value="name">Team A–Z</option>
          </select>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-[11px] min-w-[520px]">
            <thead>
              <tr className="text-slate-600 text-[9px] uppercase tracking-wider">
                <th className="text-left px-3 py-1.5 font-semibold">Team</th>
                <th className="text-right px-2 py-1.5 font-semibold" colSpan={3}>Title</th>
                <th className="text-right px-2 py-1.5 font-semibold" colSpan={3}>Advance</th>
                <th className="text-right px-2 py-1.5 font-semibold hidden sm:table-cell" colSpan={3}>Group winner</th>
              </tr>
              <tr className="text-slate-700 text-[9px]">
                <th className="px-3 py-1"></th>
                <th className="text-right px-1 py-1 font-mono font-normal">us</th>
                <th className="text-right px-1 py-1 font-mono font-normal">opta</th>
                <th className="text-right px-1 py-1 font-mono font-normal">Δ</th>
                <th className="text-right px-1 py-1 font-mono font-normal">us</th>
                <th className="text-right px-1 py-1 font-mono font-normal">opta</th>
                <th className="text-right px-1 py-1 font-mono font-normal">Δ</th>
                <th className="text-right px-1 py-1 font-mono font-normal hidden sm:table-cell">us</th>
                <th className="text-right px-1 py-1 font-mono font-normal hidden sm:table-cell">opta</th>
                <th className="text-right px-1 py-1 font-mono font-normal hidden sm:table-cell">Δ</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((t) => {
                const firstDelta = ((t.us.p_first ?? 0) - (t.opta.p_first ?? 0))
                return (
                  <tr key={t.code} className="border-t border-edge/20 hover:bg-white/[0.02]">
                    <td className="px-3 py-1.5">
                      <div className="flex items-center gap-2 min-w-0">
                        {t.flag_url && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={t.flag_url} alt="" className="w-4 h-3 rounded-[2px] ring-1 ring-white/10 shrink-0 object-cover" />
                        )}
                        <span className="text-slate-200 truncate">{t.name}</span>
                      </div>
                    </td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-200">{pct(t.us.p_title)}</td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-400">{pct(t.opta.p_title)}</td>
                    <td className="text-right px-1 py-1.5">{deltaPill(t.title_delta)}</td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-200">{pct(t.us.p_advance)}</td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-400">{pct(t.opta.p_advance)}</td>
                    <td className="text-right px-1 py-1.5">{deltaPill(t.advance_delta)}</td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-200 hidden sm:table-cell">{pct(t.us.p_first)}</td>
                    <td className="text-right font-mono tabular-nums px-1 py-1.5 text-slate-400 hidden sm:table-cell">{pct(t.opta.p_first)}</td>
                    <td className="text-right px-1 py-1.5 hidden sm:table-cell">{deltaPill(firstDelta)}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
        {sorted.length > 10 && (
          <div className="px-3 py-2 border-t border-edge/30">
            <button
              onClick={() => setShowAll((v) => !v)}
              className="text-[11px] text-emerald-400 hover:text-emerald-300 transition-colors font-medium"
            >
              {showAll ? `Show top 10` : `Show all ${sorted.length} teams →`}
            </button>
          </div>
        )}
      </div>

      <p className="px-4 py-3 text-[10px] text-slate-500 border-t border-edge/40 leading-relaxed">
        Our probabilities update live as group results land. Opta&apos;s are captured from their{" "}
        {data.opta_source ? (
          <a href={data.opta_source} target="_blank" rel="noopener" className="text-emerald-400 hover:underline">
            pre-tournament forecast
          </a>
        ) : "pre-tournament forecast"}
        {data.opta_captured && <span> on {data.opta_captured}</span>}
        . Title resolves at the final, advance + group winner resolve at the end of group stage.
      </p>
    </div>
  )
}

function DeltaRow({ t, sign }: { t: TournamentRow; sign: "+" | "-" }) {
  const color = sign === "+" ? "text-emerald-400" : "text-amber-400"
  return (
    <div className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-white/[0.03]">
      {t.flag_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={t.flag_url} alt="" className="w-5 h-[15px] rounded-[2px] ring-1 ring-white/10 shrink-0 object-cover" />
      )}
      <span className="text-[12px] text-slate-100 font-medium flex-1 truncate">{t.name}</span>
      <div className="text-right">
        <p className={`font-mono text-[11px] tabular-nums ${color}`}>
          {sign}{Math.abs(Math.round((t.title_delta || 0) * 1000) / 10)}pt
        </p>
        <p className="text-[9px] text-slate-600 font-mono">
          us {pct(t.us.p_title)} · opta {pct(t.opta.p_title)}
        </p>
      </div>
    </div>
  )
}

export function Scoreboard({
  matchData,
  tournamentData,
}: {
  matchData: MatchData | null
  tournamentData: TournamentData | null
}) {
  return (
    <div className="mb-6">
      <div className="mb-2 flex items-baseline justify-between">
        <p className="text-[10px] font-bold uppercase tracking-[0.2em] text-slate-500">Scoreboard</p>
        <p className="text-[10px] text-slate-600">Us vs the market vs the supercomputer.</p>
      </div>
      <div className="space-y-3">
        {matchData && <MatchLevelTable data={matchData} />}
        {tournamentData && <TournamentLevelTable data={tournamentData} />}
      </div>
    </div>
  )
}
