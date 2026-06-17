import type { TournamentProjection, BracketMatch, BracketTeamRef, TournamentTeam } from "@/lib/types"

function pct(p: number) {
  return `${Math.round(p * 100)}%`
}

// "1A" -> "Winners A", "2B" -> "Runners-up B", "3(ABCDF)" -> "3rd place"
function ruleLabel(rule?: string): string | null {
  if (!rule) return null
  if (rule.startsWith("1")) return `Winners ${rule.slice(1)}`
  if (rule.startsWith("2")) return `Runners-up ${rule.slice(1)}`
  if (rule.startsWith("3")) return "3rd place"
  return null
}

function Flag({ team, size = "w-5 h-[15px]" }: { team?: TournamentTeam; size?: string }) {
  if (team?.flag_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={team.flag_url} alt="" className={`${size} rounded-[2px] object-cover ring-1 ring-white/10 shrink-0`} />
  }
  return <span className={`${size} rounded-[2px] ring-1 ring-white/10 shrink-0 block`} style={{ background: team?.primary_color || "#1e293b" }} />
}

function TeamRow({
  ref_, meta, lead, championCode,
}: { ref_?: BracketTeamRef; meta: Map<string, TournamentTeam>; lead: boolean; championCode?: string }) {
  const team = ref_ ? meta.get(ref_.code) : undefined
  const isChamp = ref_?.code === championCode
  return (
    <div
      className={`flex items-center gap-1.5 px-2 py-1 ${lead ? "bg-emerald-500/10" : ""} ${
        isChamp ? "ring-1 ring-emerald-500/40 rounded" : ""
      }`}
    >
      <Flag team={team} />
      <span className={`text-[11px] truncate flex-1 ${lead ? "text-slate-100 font-semibold" : "text-slate-400"}`}>
        {team?.name ?? ref_?.code ?? "TBD"}
      </span>
      {ref_ && (
        <span className={`text-[10px] tabular-nums ${lead ? "text-emerald-400" : "text-slate-600"}`}>{pct(ref_.p)}</span>
      )}
    </div>
  )
}

function MatchCard({ m, meta, championCode }: { m: BracketMatch; meta: Map<string, TournamentTeam>; championCode?: string }) {
  const [a, b] = m.teams
  // The more likely of the two to reach this match leads the card.
  const lead = (a?.p ?? 0) >= (b?.p ?? 0) ? 0 : 1
  const rule = ruleLabel(m.home_rule) && ruleLabel(m.away_rule)
    ? `${ruleLabel(m.home_rule)} v ${ruleLabel(m.away_rule)}`
    : null
  return (
    <div className="w-[150px] rounded-lg border border-edge bg-surface-2 shadow-e1 overflow-hidden divide-y divide-edge/70">
      <TeamRow ref_={a} meta={meta} lead={lead === 0} championCode={championCode} />
      <TeamRow ref_={b} meta={meta} lead={lead === 1} championCode={championCode} />
      {rule && <p className="px-2 py-0.5 text-[8.5px] text-slate-600 truncate bg-surface-1">{rule}</p>}
    </div>
  )
}

export function BracketTree({ projection }: { projection: TournamentProjection }) {
  const bracket = projection.bracket
  if (!bracket) return null
  const meta = new Map(projection.teams.map((t) => [t.code, t]))
  const champion = projection.teams[0] // sorted by p_title desc
  const championCode = champion?.code

  return (
    <div>
      {/* Champion call-out */}
      {champion && (
        <div className="mb-4 rounded-xl border border-emerald-500/30 bg-emerald-500/5 shadow-glow p-3.5 flex items-center gap-3">
          <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400 shrink-0">Model favourite</span>
          <Flag team={champion} size="w-7 h-[21px]" />
          <span className="text-[15px] font-bold text-white truncate">{champion.name}</span>
          <span className="ml-auto text-right shrink-0">
            <span className="font-mono text-[18px] font-black text-emerald-400 tabular-nums">{pct(champion.p_title ?? 0)}</span>
            <span className="block text-[9px] uppercase tracking-wider text-slate-500">to lift it</span>
          </span>
        </div>
      )}

      {/* Bracket: rounds as columns, scroll horizontally on small screens */}
      <div className="overflow-x-auto pb-3 -mx-3 px-3">
        <div className="flex items-stretch gap-3 min-w-max">
          {bracket.rounds.map((round) => (
            <div key={round.name} className="flex flex-col min-w-[150px]">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-slate-500 mb-2 text-center">
                {round.name}
              </p>
              <div className="flex flex-col justify-around gap-2 flex-1">
                {round.matches.map((m) => (
                  <MatchCard key={m.match} m={m} meta={meta} championCode={championCode} />
                ))}
              </div>
            </div>
          ))}
        </div>
      </div>

      <p className="text-[11px] text-slate-500 leading-relaxed mt-3">
        A projection from {projection.n_sims.toLocaleString()} simulations: at each tie, the two teams most
        likely to get there, with their chance of reaching that round. Real matchups lock in as the groups
        finish. The favourite shown is the team that wins the final most often, so it always matches the
        title odds.
      </p>
    </div>
  )
}
