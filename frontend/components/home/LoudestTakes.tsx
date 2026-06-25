import Link from "next/link"
import path from "node:path"
import fs from "node:fs/promises"
import { MessageSquare, ExternalLink } from "lucide-react"

type Quote = {
  body: string
  author: string
  upvotes: number
  url: string
}

type TeamEntry = {
  quote: Quote | null
}

type MatchEntry = {
  home_code: string
  away_code: string
  match_id?: string
  quote: Quote | null
}

type LoudTake = Quote & {
  context: string
  contextHref: string
}

async function readJson<T>(rel: string): Promise<T | null> {
  try {
    const p = path.join(process.cwd(), "public", "data", rel)
    return JSON.parse(await fs.readFile(p, "utf-8")) as T
  } catch {
    return null
  }
}

const TEAM_NAME: Record<string, string> = {
  ar: "Argentina", at: "Austria", au: "Australia", ba: "Bosnia & H.",
  be: "Belgium", br: "Brazil", ca: "Canada", cd: "DR Congo",
  ch: "Switzerland", ci: "Ivory Coast", co: "Colombia", cv: "Cape Verde",
  cw: "Curacao", cz: "Czechia", de: "Germany", dz: "Algeria",
  ec: "Ecuador", eg: "Egypt", es: "Spain", fr: "France",
  "gb-eng": "England", "gb-sct": "Scotland", gh: "Ghana", hr: "Croatia",
  ht: "Haiti", iq: "Iraq", ir: "Iran", jo: "Jordan",
  jp: "Japan", kr: "South Korea", ma: "Morocco", mx: "Mexico",
  nl: "Netherlands", no: "Norway", nz: "New Zealand", pa: "Panama",
  pt: "Portugal", py: "Paraguay", qa: "Qatar", sa: "Saudi Arabia",
  se: "Sweden", sn: "Senegal", tn: "Tunisia", tr: "Turkey",
  us: "United States", uy: "Uruguay", uz: "Uzbekistan", za: "South Africa",
}

async function collectTakes(): Promise<LoudTake[]> {
  const takes: LoudTake[] = []

  const teamSnap = await readJson<{ teams: Record<string, TeamEntry> }>("team-news.json")
  if (teamSnap?.teams) {
    for (const [code, entry] of Object.entries(teamSnap.teams)) {
      if (entry.quote) {
        takes.push({
          ...entry.quote,
          context: TEAM_NAME[code] ?? code,
          contextHref: `/team/${code}`,
        })
      }
    }
  }

  const matchSnap = await readJson<{ matches: Record<string, MatchEntry> }>("match-briefs.json")
  if (matchSnap?.matches) {
    for (const [mid, brief] of Object.entries(matchSnap.matches)) {
      if (brief.quote) {
        const home = TEAM_NAME[brief.home_code] ?? brief.home_code
        const away = TEAM_NAME[brief.away_code] ?? brief.away_code
        takes.push({
          ...brief.quote,
          context: `${home} vs ${away}`,
          contextHref: `/match/${mid}`,
        })
      }
    }
  }

  // Dedup by URL (a quote shared across team + match briefs is the same content)
  const seen = new Set<string>()
  const deduped: LoudTake[] = []
  for (const t of takes.sort((a, b) => b.upvotes - a.upvotes)) {
    if (seen.has(t.url)) continue
    seen.add(t.url)
    deduped.push(t)
  }

  return deduped.slice(0, 8)
}

export async function LoudestTakes() {
  const takes = await collectTakes()
  if (takes.length === 0) return null

  return (
    <section className="mb-5 -mx-3 sm:mx-0 sm:rounded-2xl sm:border sm:border-edge sm:bg-surface-2 sm:shadow-e1 sm:p-4">
      <div className="px-3 sm:px-0 mb-2 flex items-center justify-between">
        <h2 className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-slate-500">
          <MessageSquare size={11} className="text-orange-400" />
          Loudest takes
        </h2>
        <p className="text-[10px] text-slate-600">community</p>
      </div>
      <div className="overflow-x-auto px-3 sm:px-0 -mx-px scrollbar-thin scrollbar-thumb-edge">
        <ul className="flex gap-2 pb-1 snap-x">
          {takes.map((t, i) => (
            <li
              key={t.url ?? i}
              className="shrink-0 w-[270px] snap-start rounded-xl border border-edge bg-surface-3 px-3 py-2.5"
            >
              <a
                href={t.url}
                target="_blank"
                rel="noopener noreferrer"
                className="block group"
              >
                <p className="text-[12px] italic text-slate-200 leading-snug line-clamp-3 group-hover:text-slate-100">
                  &ldquo;{t.body}&rdquo;
                </p>
                <p className="text-[10px] text-slate-500 mt-1.5 flex items-center gap-1">
                  {t.author} · {t.upvotes.toLocaleString()} upvotes
                  <ExternalLink size={9} className="opacity-60" />
                </p>
              </a>
              <Link
                href={t.contextHref}
                className="block mt-1 text-[10px] text-emerald-400 hover:text-emerald-300"
              >
                on {t.context}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </section>
  )
}
