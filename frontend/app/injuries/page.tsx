import type { Metadata } from "next"
import Link from "next/link"
import path from "node:path"
import fs from "node:fs/promises"
import { TopBar } from "@/components/layout/TopBar"
import { AlertTriangle, ExternalLink, Search } from "lucide-react"
import { InjuryViews } from "@/components/injuries/InjuryViews"

export const metadata: Metadata = {
  title: "Injuries Hub: Every Flagged Player at the 2026 World Cup",
  description:
    "Live injury and availability chatter for every team at the 2026 World Cup — sorted by severity. Sourced from community discussion and news coverage in the last 20 days.",
  alternates: { canonical: "https://wc26.tinjak.com/injuries" },
}

// Static-serve the rendered HTML and let the next deploy bring in fresh data.
// The team-news.json is rebuilt + committed by the 6am UTC cron and the deploy
// pipeline rebuilds the container, so each deploy ships a fresh snapshot.
export const dynamic = "force-static"

type Severity = "long_term" | "muscle" | "knock" | null

type Flag = {
  kind: string
  context: string
  source: string
  url: string | null
  severity?: Severity
}

type Entry = {
  flags: Flag[]
  sentiment?: string | null
}

type Snapshot = {
  updated_at: string
  team_count: number
  teams: Record<string, Entry>
}

// 48-team code -> name, same canonical list the harvester uses.
const TEAM_NAME: Record<string, string> = {
  ar: "Argentina",         at: "Austria",            au: "Australia",
  ba: "Bosnia and Herzegovina", be: "Belgium",        br: "Brazil",
  ca: "Canada",            cd: "DR Congo",           ch: "Switzerland",
  ci: "Ivory Coast",       co: "Colombia",           cv: "Cape Verde",
  cw: "Curacao",           cz: "Czechia",            de: "Germany",
  dz: "Algeria",           ec: "Ecuador",            eg: "Egypt",
  es: "Spain",             fr: "France",             "gb-eng": "England",
  "gb-sct": "Scotland",    gh: "Ghana",              hr: "Croatia",
  ht: "Haiti",             iq: "Iraq",               ir: "Iran",
  jo: "Jordan",            jp: "Japan",              kr: "South Korea",
  ma: "Morocco",           mx: "Mexico",             nl: "Netherlands",
  no: "Norway",            nz: "New Zealand",        pa: "Panama",
  pt: "Portugal",          py: "Paraguay",           qa: "Qatar",
  sa: "Saudi Arabia",      se: "Sweden",             sn: "Senegal",
  tn: "Tunisia",           tr: "Turkey",             us: "United States",
  uy: "Uruguay",           uz: "Uzbekistan",         za: "South Africa",
}

const SEVERITY_ORDER: Record<NonNullable<Severity>, number> = {
  long_term: 0, muscle: 1, knock: 2,
}

const KIND_ORDER: Record<string, number> = {
  injury: 0, "ruled out": 1, doubt: 2, miss: 3, fitness: 4, suspension: 5, "red card": 6,
}

const KIND_LABEL: Record<string, string> = {
  injury: "injury",
  doubt: "fitness doubt",
  suspension: "suspension",
  "ruled out": "ruled out",
  miss: "expected to miss",
  fitness: "fitness concern",
  "red card": "red card",
}

const SEVERITY_LABEL: Record<NonNullable<Severity>, string> = {
  long_term: "long-term",
  muscle: "muscle",
  knock: "knock",
}

const SEVERITY_CLS: Record<NonNullable<Severity>, string> = {
  long_term: "border-rose-500/40 text-rose-200 bg-rose-500/10",
  muscle:    "border-amber-500/40 text-amber-200 bg-amber-500/10",
  knock:     "border-slate-500/40 text-slate-300 bg-slate-500/10",
}

async function loadSnapshot(): Promise<Snapshot | null> {
  try {
    const p = path.join(process.cwd(), "public", "data", "team-news.json")
    const txt = await fs.readFile(p, "utf-8")
    return JSON.parse(txt) as Snapshot
  } catch {
    return null
  }
}

type FlatFlag = Flag & { teamCode: string; teamName: string }

function flattenFlags(snap: Snapshot): FlatFlag[] {
  const out: FlatFlag[] = []
  for (const [code, entry] of Object.entries(snap.teams ?? {})) {
    const name = TEAM_NAME[code] ?? code
    for (const f of entry.flags ?? []) {
      out.push({ ...f, teamCode: code, teamName: name })
    }
  }
  out.sort((a, b) => {
    const sa = a.severity ? SEVERITY_ORDER[a.severity] ?? 3 : 3
    const sb = b.severity ? SEVERITY_ORDER[b.severity] ?? 3 : 3
    if (sa !== sb) return sa - sb
    const ka = KIND_ORDER[a.kind] ?? 9
    const kb = KIND_ORDER[b.kind] ?? 9
    if (ka !== kb) return ka - kb
    return a.teamName.localeCompare(b.teamName)
  })
  return out
}

function groupByTeam(flags: FlatFlag[]): { code: string; name: string; flags: FlatFlag[] }[] {
  const map = new Map<string, FlatFlag[]>()
  for (const f of flags) {
    const list = map.get(f.teamCode) ?? []
    list.push(f)
    map.set(f.teamCode, list)
  }
  const teams = Array.from(map.entries()).map(([code, list]) => ({
    code,
    name: TEAM_NAME[code] ?? code,
    flags: list,
  }))
  // Order teams by most-severe flag, then count desc, then name asc.
  teams.sort((a, b) => {
    const sa = Math.min(...a.flags.map((f) => (f.severity ? SEVERITY_ORDER[f.severity] : 3)))
    const sb = Math.min(...b.flags.map((f) => (f.severity ? SEVERITY_ORDER[f.severity] : 3)))
    if (sa !== sb) return sa - sb
    if (b.flags.length !== a.flags.length) return b.flags.length - a.flags.length
    return a.name.localeCompare(b.name)
  })
  return teams
}

function formatUpdated(iso?: string | null): string {
  if (!iso) return "—"
  return new Date(iso).toISOString().slice(0, 16).replace("T", " ") + " UTC"
}

export default async function InjuriesHubPage() {
  const snap = await loadSnapshot()
  const flags = snap ? flattenFlags(snap) : []

  return (
    <main className="min-h-screen bg-bg text-slate-200">
      <TopBar title="Injuries Hub" />

      <div className="max-w-3xl mx-auto px-4 pt-4 pb-12">
        <header className="mb-5">
          <h1 className="text-2xl font-bold text-slate-100 mb-1">Injury & availability hub</h1>
          <p className="text-[13px] text-slate-400 leading-relaxed">
            Every flagged player across the 48 World Cup squads, harvested daily from community discussion
            and news coverage in the last 20 days. Tagged by severity where we can pick it up from the
            source text (long-term / muscle / knock).
          </p>
          {snap?.updated_at && (
            <p className="text-[11px] font-mono text-slate-600 mt-2">
              Data refreshed {formatUpdated(snap.updated_at)}
            </p>
          )}
        </header>

        {!snap && (
          <div className="rounded-2xl border border-edge bg-surface-2 p-4 text-center text-slate-400">
            Could not load injury data right now. Try refreshing in a few minutes.
          </div>
        )}

        {snap && flags.length === 0 && (
          <div className="rounded-2xl border border-edge bg-surface-2 p-6 text-center">
            <Search className="w-5 h-5 mx-auto text-slate-600 mb-2" />
            <p className="text-[13px] text-slate-400">
              No injury chatter detected in the last 20 days across the 48 squads. That&apos;s
              unusual — check back after the next refresh.
            </p>
          </div>
        )}

        {snap && flags.length > 0 && (
          <InjuryViews
            bySeverity={<BySeverityView flags={flags} />}
            byTeam={<ByTeamView teams={groupByTeam(flags)} />}
          />
        )}
      </div>
    </main>
  )
}

function BySeverityView({ flags }: { flags: FlatFlag[] }) {
  const tiers = { long_term: 0, muscle: 0, knock: 0, unknown: 0 } as Record<string, number>
  flags.forEach((f) => {
    const k = f.severity ?? "unknown"
    tiers[k] = (tiers[k] ?? 0) + 1
  })

  return (
    <>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-5">
        <SeverityTile sev="long_term" label="Long-term" count={tiers.long_term} />
        <SeverityTile sev="muscle"    label="Muscle"    count={tiers.muscle} />
        <SeverityTile sev="knock"     label="Knock"     count={tiers.knock} />
        <UnknownTile  count={tiers.unknown} />
      </div>

      <ul className="space-y-2">
        {flags.map((f, i) => (
          <FlagRow key={`${f.teamCode}-${i}`} f={f} showTeamName />
        ))}
      </ul>
    </>
  )
}

function ByTeamView({
  teams,
}: {
  teams: { code: string; name: string; flags: FlatFlag[] }[]
}) {
  return (
    <ul className="space-y-4">
      {teams.map((t) => (
        <li
          key={t.code}
          className="rounded-2xl border border-edge bg-surface-2 p-3"
        >
          <div className="flex items-baseline justify-between mb-2 px-1">
            <Link
              href={`/team/${t.code}`}
              className="text-[15px] font-semibold text-slate-100 hover:text-emerald-300"
            >
              {t.name}
            </Link>
            <span className="text-[11px] text-slate-500">
              {t.flags.length} {t.flags.length === 1 ? "flag" : "flags"}
            </span>
          </div>
          <ul className="space-y-1.5">
            {t.flags.map((f, i) => (
              <FlagRow key={`${t.code}-${i}`} f={f} showTeamName={false} />
            ))}
          </ul>
        </li>
      ))}
    </ul>
  )
}

function FlagRow({ f, showTeamName }: { f: FlatFlag; showTeamName: boolean }) {
  return (
    <li className="rounded-xl border border-edge bg-surface-3 p-3 flex items-start gap-3">
      <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0 text-amber-400" />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2 flex-wrap mb-1">
          {showTeamName && (
            <Link
              href={`/team/${f.teamCode}`}
              className="text-[13px] font-semibold text-slate-100 hover:text-emerald-300"
            >
              {f.teamName}
            </Link>
          )}
          <span className="text-[10.5px] font-medium uppercase tracking-wider text-slate-500">
            {KIND_LABEL[f.kind] ?? f.kind}
          </span>
          {f.severity && (
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider rounded-full border px-1.5 py-0.5 ${SEVERITY_CLS[f.severity]}`}
            >
              {SEVERITY_LABEL[f.severity]}
            </span>
          )}
        </div>
        <p className="text-[13px] leading-snug text-slate-300">{f.context}</p>
        {f.url && (
          <a
            href={f.url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center text-[11px] text-slate-500 hover:text-slate-300 mt-1"
          >
            Source on {f.source ?? "the web"}
            <ExternalLink className="w-3 h-3 ml-1 opacity-70" />
          </a>
        )}
      </div>
    </li>
  )
}

function SeverityTile({
  sev,
  label,
  count,
}: {
  sev: NonNullable<Severity>
  label: string
  count: number
}) {
  return (
    <div className={`rounded-xl border p-3 ${SEVERITY_CLS[sev]}`}>
      <p className="text-[10px] uppercase tracking-wider opacity-80">{label}</p>
      <p className="text-xl font-bold leading-none mt-1">{count}</p>
    </div>
  )
}

function UnknownTile({ count }: { count: number }) {
  return (
    <div className="rounded-xl border border-slate-700 bg-surface-2 p-3 text-slate-400">
      <p className="text-[10px] uppercase tracking-wider opacity-80">Unclassified</p>
      <p className="text-xl font-bold leading-none mt-1">{count}</p>
    </div>
  )
}
