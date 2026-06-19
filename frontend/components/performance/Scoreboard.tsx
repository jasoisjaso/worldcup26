/**
 * Forecaster Scoreboard — us vs Bet365 vs Opta on the same data.
 *
 * Match-level (top): scored every game where Bet365 and we both submitted a 1X2 before
 * kickoff. Brier lower = sharper. Hit rate = times the favourite outcome won.
 *
 * Tournament-level (bottom): per-team title %, advance %, group-winner %. Side-by-side
 * with Opta. Sorted by where we disagree most (those rows are the most-shareable takes).
 */

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

  const sortable = data.forecasters.filter((f) => f.brier != null)
  const us = sortable.find((f) => f.forecaster === "model_blend")
  const winner = sortable[0]
  const usIsWinning = us && winner && us.forecaster === winner.forecaster

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 flex items-center justify-between border-b border-edge/60">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/90">
          Per-match — vs the market consensus
        </p>
        <span className="text-[10px] text-slate-600 font-mono">{data.n_total_settled} match{data.n_total_settled === 1 ? "" : "es"} settled</span>
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
          {data.forecasters.map((f, i) => {
            const isUs = f.forecaster === "model_blend"
            const isLeader = i === 0 && f.brier != null
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
      <p className="px-4 py-3 text-[10px] text-slate-500 border-t border-edge/40 leading-relaxed">
        Lower Brier = sharper forecast. Hit rate = times the favourite outcome won. The market consensus is the closing line averaged across every bookmaker we track and Shin-devigged. We score every settled match the same way for everybody — no cherry-picking.
        {usIsWinning && (
          <span className="ml-1 text-emerald-400 font-semibold">We&apos;re ahead of the market right now.</span>
        )}
      </p>
    </div>
  )
}

function TournamentLevelTable({ data }: { data: TournamentData }) {
  if (data.n_teams === 0) {
    return null
  }
  const top = data.teams.slice(0, 8)
  const us_higher = top.filter((t) => (t.title_delta ?? 0) > 0).slice(0, 4)
  const us_lower = top.filter((t) => (t.title_delta ?? 0) < 0).slice(0, 4)

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      <div className="px-4 pt-3.5 pb-2 flex items-center justify-between border-b border-edge/60">
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/90">
          Tournament-level — vs the Opta supercomputer
        </p>
        <span className="text-[10px] text-slate-600 font-mono">{data.n_teams} teams</span>
      </div>

      <div className="grid sm:grid-cols-2 gap-3 p-3">
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-emerald-400/80 mb-1.5 px-1">
            We&apos;re more bullish on
          </p>
          <div className="space-y-1">
            {us_higher.map((t) => (
              <DeltaRow key={t.code} t={t} sign="+" />
            ))}
            {us_higher.length === 0 && (
              <p className="text-[11px] text-slate-600 px-1">No teams where we're more bullish in the top 8 disagreements.</p>
            )}
          </div>
        </div>
        <div>
          <p className="text-[10px] font-bold uppercase tracking-wider text-amber-400/80 mb-1.5 px-1">
            We&apos;re more cautious on
          </p>
          <div className="space-y-1">
            {us_lower.map((t) => (
              <DeltaRow key={t.code} t={t} sign="-" />
            ))}
            {us_lower.length === 0 && (
              <p className="text-[11px] text-slate-600 px-1">No teams where we're more cautious in the top 8 disagreements.</p>
            )}
          </div>
        </div>
      </div>

      <p className="px-4 py-3 text-[10px] text-slate-500 border-t border-edge/40 leading-relaxed">
        Title probabilities — ours from {(data.teams[0] ? "20,000 simulations" : "—")}, Opta&apos;s captured from their{" "}
        {data.opta_source ? (
          <a href={data.opta_source} target="_blank" rel="noopener" className="text-emerald-400 hover:underline">
            pre-tournament forecast
          </a>
        ) : "pre-tournament forecast"}.
        These resolve into hit / miss only as the tournament progresses; for now it&apos;s where we disagree and why anyone should care.
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
