import Link from "next/link"
import { Ban } from "lucide-react"
import { ShootoutTracker } from "@/components/live/ShootoutTracker"

/**
 * MatchRecap — the post-match (or in-play) "what happened" panel.
 *
 * Six sections, each self-handling its empty state so we never render an empty
 * card or a "stats not available" stub when there's just nothing yet:
 *   1. Goals timeline — minute + scorer + assist + team flag
 *   2. Cards summary — yellow / red counts per team
 *   3. Stats compare — possession, shots, on target, xG, corners, fouls, etc.
 *   4. Top performer (MOTM) — auto-picked top scorer with team link
 *   5. Lineups — formation + starters (collapsed below the fold)
 *
 * All data is read from the recap endpoint; the parent decides whether to
 * render this at all (we hide entirely when recap.has_content is false).
 */

interface Stats {
  possession_pct: number | null
  shots_total: number | null
  shots_on_target: number | null
  shots_off_target: number | null
  shots_blocked: number | null
  shots_inside_box: number | null
  shots_outside_box: number | null
  corners: number | null
  fouls: number | null
  offsides: number | null
  yellow_cards: number | null
  red_cards: number | null
  saves: number | null
  passes_total: number | null
  passes_accurate: number | null
  passes_pct: number | null
  xg: number | null
}

interface TeamRecap {
  code: string | null
  name: string
  flag_url: string | null
  stats: Stats | null
  lineup: {
    formation: string | null
    coach: string | null
    starters: Array<{
      player_id: number | null
      player_name: string
      number: number | null
      position: string | null
      grid: string | null
    }>
    bench: Array<{
      player_id: number | null
      player_name: string
      number: number | null
      position: string | null
    }>
  } | null
}

interface RecapEvent {
  minute: number
  elapsed: number | null
  extra: number | null
  type: string
  detail: string
  player_id: number | null
  player_name: string | null
  assist_name: string | null
  team_side: "home" | "away" | null
  team_name: string | null
  // True when api-football's subsequent Var event marked this Goal as
  // disallowed. The timeline renders the row with strikethrough + VAR tag,
  // and the goal count in the section header reflects the post-VAR total.
  var_disallowed?: boolean
  // Reason VAR overturned the goal (e.g. "Foul", "Offside"). Used by the
  // timeline so a user who didn't watch the match still understands what
  // happened on the review.
  var_reason?: string | null
}

interface Recap {
  match_id: string
  status: string
  is_complete: boolean
  has_content: boolean
  score: { home: number | null; away: number | null } | null
  // Shootout tiebreaker. Null for matches decided in regulation/ET; present
  // for knockouts that went to penalties. When set, the recap renders a
  // shootout breakdown card at the top of the timeline (dot row per team +
  // optional per-kick log) so a user opening the page post-match sees what
  // happened on penalties, not just "FT 1-1".
  shootout_score?: { home: number | null; away: number | null } | null
  home: TeamRecap
  away: TeamRecap
  events: RecapEvent[]
  motm: { player_id: number | null; name: string; goals: number; side: "home" | "away" | null; team_name: string | null } | null
}

function Section({ title, children, dense }: { title: string; children: React.ReactNode; dense?: boolean }) {
  return (
    <div className={`rounded-2xl border border-edge bg-surface-2 shadow-e1 ${dense ? "p-3.5" : "p-4"}`}>
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-3">{title}</p>
      {children}
    </div>
  )
}

function GoalsTimeline({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  // api-football packs scored goals + missed pens into the same type="Goal".
  // Split them so the "Goals" section only shows actual goals; missed pens
  // get their own block right below (since they're a high-leverage betting
  // signal — e.g. who's stepping up in a shootout next round).
  const goals = events.filter((e) => e.type === "Goal" && e.detail !== "Missed Penalty")
  // Section count reflects POST-VAR total. The disallowed rows still render
  // (with strikethrough + VAR tag) so the punter sees what actually happened
  // on the pitch and isn't confused by 'why is the score X when 3 goals are
  // listed'.
  const validGoalCount = goals.filter((g) => !g.var_disallowed).length
  if (goals.length === 0) {
    return (
      <Section title="Goals">
        <p className="text-[12px] text-slate-600">No goals scored.</p>
      </Section>
    )
  }
  return (
    <Section title={`Goals (${validGoalCount})`}>
      <div className="space-y-2">
        {goals.map((g, i) => {
          const isHome = g.team_side === "home"
          const flag = isHome ? home.flag_url : away.flag_url
          const teamLabel = isHome ? home.name : away.name
          const isOwn = (g.detail || "").toLowerCase().includes("own")
          const isPen = (g.detail || "").toLowerCase() === "penalty"
          const disallowed = !!g.var_disallowed
          // Reason text for the VAR row, e.g. "Foul" / "Offside". When missing
          // we fall back to a generic phrasing.
          const varReason = (g.var_reason || "").toLowerCase()
          return (
            <div
              key={i}
              className={`flex items-start gap-3 text-[12.5px] ${disallowed ? "" : ""}`}
            >
              <span className="font-mono tabular-nums text-slate-500 w-10 shrink-0 pt-0.5">{g.minute}&apos;</span>
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0 mt-1" />
              )}
              <div className="flex-1 min-w-0">
                <p
                  className={`font-semibold truncate flex items-center gap-1.5 ${
                    disallowed ? "text-slate-400 line-through" : "text-slate-100"
                  }`}
                >
                  {g.player_id ? (
                    <Link href={`/player/${g.player_id}`} className={`truncate ${disallowed ? "" : "hover:text-emerald-300"}`}>
                      {g.player_name}
                    </Link>
                  ) : (
                    <span className="truncate">{g.player_name}</span>
                  )}
                  {isPen && <span className="text-[9px] text-amber-400 font-mono uppercase tracking-wider no-underline">pen</span>}
                  {isOwn && <span className="text-[9px] text-rose-400 font-mono uppercase tracking-wider no-underline">og</span>}
                </p>
                {disallowed && (
                  // Explicit second-line VAR notice. Much more legible than a
                  // tiny inline badge: full red, no strikethrough, plain
                  // English. A user reading the timeline cold knows exactly
                  // what happened on the review.
                  <p className="text-[10.5px] text-rose-400 font-semibold leading-snug mt-0.5">
                    ⚠ VAR overturned this goal{varReason ? ` (${varReason})` : ""}.
                  </p>
                )}
                {g.assist_name && !isOwn && (
                  <p className={`text-[10px] truncate ${disallowed ? "text-slate-600 line-through" : "text-slate-500"}`}>
                    assist: {g.assist_name}
                  </p>
                )}
              </div>
              <span className="text-[10px] text-slate-600 shrink-0">{teamLabel}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function MissedPenaltiesTimeline({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  const misses = events.filter((e) => e.type === "Goal" && e.detail === "Missed Penalty")
  if (misses.length === 0) return null
  return (
    <Section title={`Missed penalties (${misses.length})`}>
      <div className="space-y-2">
        {misses.map((m, i) => {
          const isHome = m.team_side === "home"
          const flag = isHome ? home.flag_url : away.flag_url
          const teamLabel = isHome ? home.name : away.name
          return (
            <div key={i} className="flex items-center gap-3 text-[12.5px]">
              <span className="font-mono tabular-nums text-slate-500 w-10 shrink-0">{m.minute}&apos;</span>
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
              )}
              <Ban size={14} className="shrink-0 text-rose-400" aria-hidden />
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 font-semibold truncate flex items-center gap-1.5">
                  {m.player_id ? (
                    <Link href={`/player/${m.player_id}`} className="hover:text-rose-300 truncate">{m.player_name}</Link>
                  ) : (
                    <span className="truncate">{m.player_name}</span>
                  )}
                  <span className="text-[9px] text-rose-400 font-mono uppercase tracking-wider">miss</span>
                </p>
              </div>
              <span className="text-[10px] text-slate-600 shrink-0">{teamLabel}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function CardsTimeline({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  const cards = events.filter((e) => e.type === "Card")
  if (cards.length === 0) return null
  return (
    <Section title={`Cards (${cards.length})`}>
      <div className="space-y-2">
        {cards.map((c, i) => {
          const isHome = c.team_side === "home"
          const flag = isHome ? home.flag_url : away.flag_url
          const teamLabel = isHome ? home.name : away.name
          const isYellow = (c.detail || "").toLowerCase().includes("yellow")
          const isRed = (c.detail || "").toLowerCase().includes("red")
          return (
            <div key={i} className="flex items-center gap-3 text-[12.5px]">
              <span className="font-mono tabular-nums text-slate-500 w-10 shrink-0">{c.minute}&apos;</span>
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
              )}
              {/* Apple Sports style card glyph: small filled rectangle. Functional,
                  not decorative, so it stays. Falls back to a dot for non-card events. */}
              <span aria-hidden className="shrink-0">
                {isRed ? <span className="inline-block w-[8px] h-[11px] bg-rose-500 rounded-[1px]" />
                : isYellow ? <span className="inline-block w-[8px] h-[11px] bg-amber-400 rounded-[1px]" />
                : <span className="text-slate-600">·</span>}
              </span>
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 font-semibold truncate">
                  {c.player_name || "Team booking"}
                </p>
                {c.detail && c.detail !== "Yellow Card" && c.detail !== "Red Card" && (
                  <p className="text-[10px] text-slate-500 truncate">{c.detail}</p>
                )}
              </div>
              <span className="text-[10px] text-slate-600 shrink-0">{teamLabel}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}


function SubsTimeline({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  // api-football encodes subs as type="subst" with player_name = the player
  // coming OFF and assist_name = the player coming ON.
  const subs = events.filter((e) => (e.type || "").toLowerCase() === "subst")
  if (subs.length === 0) return null
  return (
    <Section title={`Substitutions (${subs.length})`}>
      <div className="space-y-2">
        {subs.map((s, i) => {
          const isHome = s.team_side === "home"
          const flag = isHome ? home.flag_url : away.flag_url
          const teamLabel = isHome ? home.name : away.name
          return (
            <div key={i} className="flex items-center gap-3 text-[12.5px]">
              <span className="font-mono tabular-nums text-slate-500 w-10 shrink-0">{s.minute}&apos;</span>
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 text-[12px]">
                  {s.assist_name ? (
                    <>
                      <span className="text-emerald-300">↑ {s.assist_name}</span>
                      <span className="text-slate-600"> for </span>
                      <span className="text-slate-400">{s.player_name || "?"}</span>
                    </>
                  ) : (
                    <span className="text-slate-300">Substitution: {s.player_name || "?"}</span>
                  )}
                </p>
              </div>
              <span className="text-[10px] text-slate-600 shrink-0">{teamLabel}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function StatBar({
  label, home, away, format = "int",
}: {
  label: string
  home: number | null | undefined
  away: number | null | undefined
  format?: "int" | "float" | "pct"
}) {
  if (home == null && away == null) return null
  const h = home ?? 0, a = away ?? 0
  const total = h + a
  const hPct = total > 0 ? (h / total) * 100 : 50
  const fmt = (v: number | null | undefined) => {
    if (v == null) return "-"
    if (format === "float") return v.toFixed(2)
    if (format === "pct") return `${Math.round(v)}%`
    return String(Math.round(v))
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-mono tabular-nums">
        <span className={h > a ? "text-white font-bold" : "text-slate-400"}>{fmt(home)}</span>
        <span className="text-[9px] text-slate-600 uppercase tracking-wider font-sans">{label}</span>
        <span className={a > h ? "text-white font-bold" : "text-slate-400"}>{fmt(away)}</span>
      </div>
      <div className="flex h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="bg-emerald-500/70" style={{ width: `${hPct}%` }} />
        <div className="bg-orange-500/70" style={{ width: `${100 - hPct}%` }} />
      </div>
    </div>
  )
}

function StatsCompare({ home, away }: { home: Stats | null; away: Stats | null }) {
  if (!home && !away) return null
  return (
    <Section title="Match stats">
      <div className="space-y-2.5">
        <StatBar label="Possession" home={home?.possession_pct ?? null} away={away?.possession_pct ?? null} format="pct" />
        <StatBar label="Shots" home={home?.shots_total ?? null} away={away?.shots_total ?? null} />
        <StatBar label="Shots on target" home={home?.shots_on_target ?? null} away={away?.shots_on_target ?? null} />
        {(home?.xg != null || away?.xg != null) && (
          <StatBar label="Expected goals" home={home?.xg ?? null} away={away?.xg ?? null} format="float" />
        )}
        <StatBar label="Corners" home={home?.corners ?? null} away={away?.corners ?? null} />
        <StatBar label="Fouls" home={home?.fouls ?? null} away={away?.fouls ?? null} />
        <StatBar label="Offsides" home={home?.offsides ?? null} away={away?.offsides ?? null} />
        <StatBar label="Saves" home={home?.saves ?? null} away={away?.saves ?? null} />
        <StatBar label="Pass accuracy" home={home?.passes_pct ?? null} away={away?.passes_pct ?? null} format="pct" />
      </div>
    </Section>
  )
}

function MotmCard({ motm }: { motm: NonNullable<Recap["motm"]> }) {
  return (
    <Section title="Top performer" dense>
      <Link
        href={motm.player_id ? `/player/${motm.player_id}` : "#"}
        className="flex items-center gap-3 group"
      >
        <span className="w-12 h-12 rounded-full bg-gradient-to-br from-amber-500/30 to-amber-700/10 ring-2 ring-amber-500/30 flex items-center justify-center text-amber-300 font-black text-[15px] shrink-0">
          {motm.name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase()}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-bold text-white truncate group-hover:text-amber-300 transition-colors">{motm.name}</p>
          <p className="text-[11px] text-slate-500 truncate">
            {motm.team_name ? `${motm.team_name} · ` : ""}
            {motm.goals} {motm.goals === 1 ? "goal" : "goals"}
          </p>
        </div>
      </Link>
    </Section>
  )
}

function LineupsBlock({ home, away }: { home: TeamRecap; away: TeamRecap }) {
  if (!home.lineup && !away.lineup) return null
  return (
    <Section title="Lineups">
      <div className="grid grid-cols-2 gap-4 text-[11px]">
        {[home, away].map((team, i) => (
          <div key={i} className="min-w-0">
            <p className="text-[10px] font-bold text-slate-300 mb-2 truncate flex items-center gap-1.5">
              {team.flag_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={team.flag_url} alt="" className="w-4 h-3 rounded-[1px] object-cover shrink-0" />
              )}
              <span className="truncate">{team.name}</span>
              {team.lineup?.formation && (
                <span className="text-slate-600 font-mono shrink-0">{team.lineup.formation}</span>
              )}
            </p>
            {team.lineup?.starters?.length ? (
              <ul className="space-y-1">
                {team.lineup.starters.map((p) => (
                  <li key={`${p.player_id ?? p.player_name}-${p.number ?? ""}`} className="flex items-center gap-2 text-slate-400">
                    {p.number != null && <span className="text-slate-600 font-mono tabular-nums w-5 text-right shrink-0">{p.number}</span>}
                    {p.player_id ? (
                      <Link href={`/player/${p.player_id}`} className="truncate hover:text-emerald-300">{p.player_name}</Link>
                    ) : (
                      <span className="truncate">{p.player_name}</span>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-slate-600 text-[10px]">Lineup not available.</p>
            )}
          </div>
        ))}
      </div>
    </Section>
  )
}

export function MatchRecap({ recap }: { recap: Recap }) {
  if (!recap.has_content) return null
  // Shape the recap's shootout score into the ShootoutTracker contract. We
  // pass status="PEN" so the tracker renders the "Decided on penalties" badge
  // (rather than the live "Shootout in progress" pulse) — it's a post-match
  // view at this point. Regulation score falls back to 0 only if the recap
  // came back without a score block, which means the match was somehow
  // marked complete without scores; in that case the breakdown is still
  // useful but the regulation line will read 0-0.
  const showShootout =
    recap.shootout_score != null &&
    (recap.shootout_score.home != null || recap.shootout_score.away != null)
  return (
    <div className="space-y-4">
      {showShootout && (
        <div className="rounded-2xl border border-amber-500/30 bg-surface-2 shadow-e1 overflow-hidden">
          <ShootoutTracker
            homeName={recap.home.name}
            awayName={recap.away.name}
            homeFlag={recap.home.flag_url}
            awayFlag={recap.away.flag_url}
            shootoutHomeScore={recap.shootout_score!.home}
            shootoutAwayScore={recap.shootout_score!.away}
            regulationHome={recap.score?.home ?? 0}
            regulationAway={recap.score?.away ?? 0}
            events={recap.events.map(e => ({
              elapsed: e.elapsed ?? 0,
              extra: e.extra ?? null,
              type: e.type,
              detail: e.detail,
              player_name: e.player_name,
              team_name: e.team_name,
            }))}
            status="PEN"
          />
        </div>
      )}
      <GoalsTimeline events={recap.events} home={recap.home} away={recap.away} />
      <MissedPenaltiesTimeline events={recap.events} home={recap.home} away={recap.away} />
      <CardsTimeline events={recap.events} home={recap.home} away={recap.away} />
      <SubsTimeline events={recap.events} home={recap.home} away={recap.away} />
      <StatsCompare home={recap.home.stats} away={recap.away.stats} />
      {recap.motm && <MotmCard motm={recap.motm} />}
      {(recap.home.lineup || recap.away.lineup) && <LineupsBlock home={recap.home} away={recap.away} />}
    </div>
  )
}
