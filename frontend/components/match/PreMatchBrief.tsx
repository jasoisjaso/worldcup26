import Link from "next/link"
import { Flag } from "@/components/common/Flag"
import type { PreMatchContext, FormRow, TeamSeasonStats, H2HSummary } from "@/lib/types"

interface Props {
  ctx: PreMatchContext
  homeName: string
  awayName: string
  homeCode: string
  awayCode: string
}

// One dense tile above the markets sheet — stakes, paired stat-comparison,
// last-5 form per side, H2H, absences, model-swing-from-absences. Replaces
// the bottom-of-page <HeadToHead/> which is now embedded here.
//
// Honest sample-size handling: when a stat has < 3 matches in the sample
// we render a "—" instead of an average so we don't pretend to know
// something we don't. matches_sampled is shown alongside every stat row.
export function PreMatchBrief({ ctx, homeName, awayName, homeCode, awayCode }: Props) {
  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5 space-y-5">
      {/* 1) Stakes */}
      <div>
        <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">What's at stake</p>
        <p className="text-[13px] text-slate-200 leading-snug">{ctx.stakes}</p>
      </div>

      {/* 2) Stat comparison */}
      <StatCompare
        home={ctx.season_stats.home}
        away={ctx.season_stats.away}
      />

      {/* 3) Form rows */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <FormColumn label={homeName} form={ctx.home_form} side="home" />
        <FormColumn label={awayName} form={ctx.away_form} side="away" />
      </div>

      {/* 4) H2H */}
      <H2HInline summary={ctx.h2h_summary} homeName={homeName} awayName={awayName} />

      {/* 5) Absences */}
      <AbsencesBlock
        homeName={homeName}
        awayName={awayName}
        homeAbsences={ctx.home_absences}
        awayAbsences={ctx.away_absences}
        swing={ctx.model_swing_from_absences}
      />
    </section>
  )
}


// ============================================================================
// Stat comparison — paired bars, FotMob-style. Higher value is coloured.
// ============================================================================

const STATS: Array<{
  key: keyof TeamSeasonStats
  label: string
  fmt: (v: number) => string
  // 'higher' = higher is better, 'lower' = lower is better,
  // 'neutral' = colour both sides slate (e.g. possession)
  direction: "higher" | "lower" | "neutral"
}> = [
  { key: "goals_per_match",      label: "Goals / match",      fmt: (v) => v.toFixed(2), direction: "higher" },
  { key: "conceded_per_match",   label: "Conceded / match",   fmt: (v) => v.toFixed(2), direction: "lower" },
  { key: "btts_pct",             label: "BTTS rate",          fmt: (v) => `${Math.round(v * 100)}%`, direction: "neutral" },
  { key: "cs_pct",               label: "Clean sheet rate",   fmt: (v) => `${Math.round(v * 100)}%`, direction: "higher" },
  { key: "xg_per_match",         label: "xG / match (club)",  fmt: (v) => v.toFixed(2), direction: "higher" },
  { key: "corners_per_match",    label: "Corners / match",    fmt: (v) => v.toFixed(1), direction: "neutral" },
  { key: "yellow_per_match",     label: "Yellows / match",    fmt: (v) => v.toFixed(1), direction: "lower" },
  { key: "possession_avg",       label: "Possession",         fmt: (v) => `${Math.round(v)}%`, direction: "neutral" },
]

function StatCompare({ home, away }: { home: TeamSeasonStats; away: TeamSeasonStats }) {
  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">Season form comparison</p>
        <p className="text-[10px] font-mono text-slate-600">
          sample home {home.matches_sampled} · away {away.matches_sampled}
        </p>
      </div>
      <div className="space-y-1.5">
        {STATS.map(({ key, label, fmt, direction }) => {
          const h = (home as unknown as Record<string, unknown>)[String(key)]
          const a = (away as unknown as Record<string, unknown>)[String(key)]
          const hNum = typeof h === "number" ? h : null
          const aNum = typeof a === "number" ? a : null
          const max = Math.max(hNum ?? 0, aNum ?? 0, 0.001)
          const homeBetter =
            direction === "neutral" || hNum == null || aNum == null
              ? false
              : direction === "higher"
              ? hNum > aNum
              : hNum < aNum
          const awayBetter =
            direction === "neutral" || hNum == null || aNum == null
              ? false
              : direction === "higher"
              ? aNum > hNum
              : aNum < hNum
          return (
            <div key={key as string} className="grid grid-cols-[3.5rem_1fr_5.5rem_1fr_3.5rem] gap-1.5 items-center text-[11px]">
              <span className={`text-right tabular-nums ${homeBetter ? "text-emerald-300" : "text-slate-400"}`}>
                {hNum == null ? "—" : fmt(hNum)}
              </span>
              <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden flex justify-end">
                {hNum != null && (
                  <div
                    className={`h-full ${homeBetter ? "bg-emerald-500" : "bg-slate-600"}`}
                    style={{ width: `${Math.min(100, (hNum / max) * 100)}%` }}
                  />
                )}
              </div>
              <span className="text-[9px] text-slate-500 text-center uppercase tracking-wider truncate" title={label}>
                {label}
              </span>
              <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                {aNum != null && (
                  <div
                    className={`h-full ${awayBetter ? "bg-orange-500" : "bg-slate-600"}`}
                    style={{ width: `${Math.min(100, (aNum / max) * 100)}%` }}
                  />
                )}
              </div>
              <span className={`text-left tabular-nums ${awayBetter ? "text-orange-300" : "text-slate-400"}`}>
                {aNum == null ? "—" : fmt(aNum)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}


// ============================================================================
// Form column — last-5 results for one side
// ============================================================================

const RESULT_COLORS: Record<string, string> = {
  W: "bg-emerald-600 text-white border-emerald-500/40",
  L: "bg-rose-700 text-white border-rose-600/40",
  D: "bg-slate-600 text-white border-slate-500/40",
}

function fmtShortDate(iso: string | null) {
  if (!iso) return ""
  try {
    return new Date(iso).toLocaleDateString("en-AU", { month: "short", day: "numeric" })
  } catch {
    return iso.slice(5, 10)
  }
}

function FormColumn({ label, form, side }: { label: string; form: FormRow[]; side: "home" | "away" }) {
  return (
    <div>
      <p className={`text-[11px] font-semibold mb-1.5 truncate ${side === "home" ? "text-emerald-300" : "text-orange-300"}`}>
        {label} · last {form.length}
      </p>
      {form.length === 0 ? (
        <p className="text-[11px] text-slate-600">No completed matches yet.</p>
      ) : (
        <div className="divide-y divide-edge border border-edge rounded-lg overflow-hidden bg-surface-1">
          {form.map((g) => {
            const chip = g.result ? RESULT_COLORS[g.result] : "bg-slate-800 text-slate-500 border-slate-700"
            return (
              <Link
                key={g.match_id}
                href={`/match/${g.match_id}`}
                className="flex items-center gap-1.5 px-2 py-1.5 hover:bg-surface-3/40 transition-colors"
              >
                <span className={`w-5 h-5 shrink-0 rounded text-[9px] font-bold flex items-center justify-center border ${chip}`}>
                  {g.result ?? "?"}
                </span>
                <span className="text-[9px] text-slate-600 uppercase tracking-wider w-2.5 shrink-0">
                  {g.venue}
                </span>
                <Flag code={g.opponent_code} name={g.opponent_name} size="sm" />
                <span className="text-[11px] text-slate-300 flex-1 truncate">{g.opponent_name}</span>
                <span className="text-[11px] font-mono tabular-nums text-slate-100 shrink-0">{g.score}</span>
                {g.kickoff && (
                  <span className="text-[9px] font-mono text-slate-600 shrink-0">{fmtShortDate(g.kickoff)}</span>
                )}
              </Link>
            )
          })}
        </div>
      )}
    </div>
  )
}


// ============================================================================
// H2H inline summary
// ============================================================================

function H2HInline({ summary, homeName, awayName }: { summary: H2HSummary; homeName: string; awayName: string }) {
  if (summary.meetings === 0) {
    return (
      <div>
        <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Head to head</p>
        <p className="text-[11px] text-slate-600">No previous meetings on record.</p>
      </div>
    )
  }
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Head to head · {summary.meetings} meetings</p>
      <div className="grid grid-cols-3 gap-1 text-center mb-2">
        <div className="bg-emerald-950/40 border border-emerald-900/40 rounded px-2 py-1.5">
          <p className="text-[18px] font-display tabular-nums text-emerald-300">{summary.home_wins}</p>
          <p className="text-[9px] text-slate-500 uppercase tracking-wider truncate">{homeName} wins</p>
        </div>
        <div className="bg-surface-3 border border-edge rounded px-2 py-1.5">
          <p className="text-[18px] font-display tabular-nums text-slate-200">{summary.draws}</p>
          <p className="text-[9px] text-slate-500 uppercase tracking-wider">Draws</p>
        </div>
        <div className="bg-orange-950/40 border border-orange-900/40 rounded px-2 py-1.5">
          <p className="text-[18px] font-display tabular-nums text-orange-300">{summary.away_wins}</p>
          <p className="text-[9px] text-slate-500 uppercase tracking-wider truncate">{awayName} wins</p>
        </div>
      </div>
      <div className="flex items-center justify-between gap-2 text-[10px] text-slate-500">
        {summary.last && <span className="truncate" title={summary.last}>Last: {summary.last}</span>}
        {summary.agg_goals_per_meeting != null && (
          <span className="font-mono tabular-nums shrink-0">
            avg {summary.agg_goals_per_meeting.toFixed(1)} goals
          </span>
        )}
      </div>
    </div>
  )
}


// ============================================================================
// Absences block — names when we have them, count otherwise, + model swing
// ============================================================================

interface AbsenceEntry {
  name: string | null
  reason: string
  count: number
}

function AbsencesBlock({
  homeName, awayName, homeAbsences, awayAbsences, swing,
}: {
  homeName: string
  awayName: string
  homeAbsences: AbsenceEntry[]
  awayAbsences: AbsenceEntry[]
  swing: PreMatchContext["model_swing_from_absences"]
}) {
  const hasAny = homeAbsences.length > 0 || awayAbsences.length > 0
  const swingHomePP = swing && "home_pp" in swing ? swing.home_pp : null
  const swingAwayPP = swing && "away_pp" in swing ? swing.away_pp : null

  if (!hasAny && swingHomePP == null && swingAwayPP == null) {
    return (
      <div>
        <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">Absences</p>
        <p className="text-[11px] text-slate-600">No known absences.</p>
      </div>
    )
  }

  return (
    <div>
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">Absences</p>
        {(swingHomePP != null || swingAwayPP != null) && (
          <p
            className="text-[10px] font-mono text-slate-500"
            title="Model win-probability swing from known absences vs a hypothetical full-strength XI"
          >
            model swing: {fmtSwingPP(swingHomePP)} / {fmtSwingPP(swingAwayPP)} pp
          </p>
        )}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <AbsenceSide name={homeName} entries={homeAbsences} accent="emerald" />
        <AbsenceSide name={awayName} entries={awayAbsences} accent="orange" />
      </div>
    </div>
  )
}

function fmtSwingPP(pp: number | null): string {
  if (pp == null) return "—"
  if (pp === 0) return "0"
  const sign = pp > 0 ? "+" : ""
  return `${sign}${pp.toFixed(1)}`
}

function AbsenceSide({
  name, entries, accent,
}: {
  name: string
  entries: AbsenceEntry[]
  accent: "emerald" | "orange"
}) {
  const accentText = accent === "emerald" ? "text-emerald-300" : "text-orange-300"
  return (
    <div>
      <p className={`text-[11px] font-semibold mb-1 truncate ${accentText}`}>{name}</p>
      {entries.length === 0 ? (
        <p className="text-[11px] text-slate-600">No known absences.</p>
      ) : (
        <ul className="space-y-1">
          {entries.map((e, i) => (
            <li key={i} className="text-[11px] text-slate-300 border border-edge bg-surface-1 rounded px-2 py-1">
              <span className="font-semibold">{e.name || `${e.count} player${e.count === 1 ? "" : "s"}`}</span>
              <span className="text-slate-500"> · {e.reason}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
