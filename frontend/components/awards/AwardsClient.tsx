"use client"
import { useEffect, useState } from "react"
import Link from "next/link"
import { Confetti } from "@/components/awards/Confetti"

interface AwardEntry {
  player_name?: string
  team_name?: string
  team_code?: string
  goals?: number
  assists?: number
  minutes?: number
  penalty_goals?: number
  appearances?: number
  saves?: number
  games?: number
  yellow_cards?: number
  red_cards?: number
  card_points?: number
  matches_played?: number
  wins?: number
  draws?: number
  losses?: number
  goals_for?: number
  goals_against?: number
  gd?: number
  clean_sheets?: number
  points?: number
  goals_per_game?: number
  flag_url?: string | null
  primary_color?: string | null
  // Upset fields
  match_id?: string
  winner?: string
  loser?: string
  winner_code?: string
  loser_code?: string
  elo_gap?: number
  score?: string
  venue?: string
  home?: string
  away?: string
  home_code?: string
  away_code?: string
  went_to_pens?: boolean
  red_cards_count?: number
  total_goals?: number
  drama_score?: number
  elo?: number
  max_round_reached?: number
  name?: string
  code?: string
  shootout?: string
}

interface AwardsData {
  golden_boot: AwardEntry[]
  most_assists: AwardEntry[]
  golden_glove: AwardEntry[]
  most_cards: AwardEntry[]
  fair_play: AwardEntry[]
  best_team: AwardEntry[]
  top_scoring_team: AwardEntry[]
  biggest_upset: AwardEntry[]
  match_of_tournament: AwardEntry[]
  most_disappointing: AwardEntry[]
  _meta: {
    matches_complete: number
    final_complete: boolean
    champion: (AwardEntry & { score?: string; shootout?: string }) | null
  }
}

function Flag({ url, color, size = "w-5 h-[15px]" }: { url?: string | null; color?: string | null; size?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${size} rounded-[2px] object-cover ring-1 ring-white/10 shrink-0`} />
  }
  return <span className={`${size} rounded-[2px] ring-1 ring-white/10 shrink-0 block`} style={{ background: color || "#1e293b" }} />
}

function AwardCard({
  icon, title, subtitle, entries, render,
}: {
  icon: string
  title: string
  subtitle: string
  entries: AwardEntry[]
  render: (e: AwardEntry, i: number) => React.ReactNode
}) {
  if (!entries || entries.length === 0) return null
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="text-[20px]">{icon}</span>
        <div>
          <p className="text-[13px] font-bold text-slate-100">{title}</p>
          <p className="text-[10px] text-slate-500">{subtitle}</p>
        </div>
      </div>
      <div className="space-y-1.5">
        {entries.map((e, i) => render(e, i))}
      </div>
    </div>
  )
}

function Row({ rank, children, highlight }: { rank: number; children: React.ReactNode; highlight?: boolean }) {
  return (
    <div className={`flex items-center gap-2 px-2 py-1.5 rounded-lg text-[11px] ${
      highlight ? "bg-amber-500/10 border border-amber-500/20" : ""
    }`}>
      <span className={`font-mono tabular-nums w-5 text-center ${highlight ? "text-amber-400 font-bold" : "text-slate-600"}`}>
        {rank}
      </span>
      {children}
    </div>
  )
}

export function AwardsClient({ initialData }: { initialData: AwardsData }) {
  const [data, setData] = useState(initialData)
  const meta = data._meta

  // Poll for updates (so the page refreshes when the final completes)
  useEffect(() => {
    const id = setInterval(async () => {
      try {
        const res = await fetch("/api/tournament/awards", { cache: "no-store" })
        if (res.ok) {
          const next = await res.json()
          setData(next)
        }
      } catch { /* silent */ }
    }, 60_000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="max-w-4xl mx-auto px-3 sm:px-5 py-5">
      <Confetti fire={meta.final_complete} />

      {/* Champion hero */}
      {meta.champion && (
        <div className="mb-6 text-center rounded-3xl border border-amber-400/30 bg-gradient-to-b from-amber-400/10 to-surface-2/20 p-8">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-amber-400/80 mb-2">
            {meta.final_complete ? "World Cup 2026 Champions" : "Tournament in progress"}
          </p>
          <div className="flex items-center justify-center gap-3 mb-2">
            <Flag url={meta.champion.flag_url} color={meta.champion.primary_color} size="w-12 h-9" />
            <h1 className="text-[32px] sm:text-[40px] font-black tracking-tight text-white">
              {meta.champion.name}
            </h1>
          </div>
          {meta.champion.score && (
            <p className="text-[14px] font-mono text-slate-400">
              {meta.champion.score}{meta.champion.shootout ? ` (${meta.champion.shootout} pens)` : ""}
            </p>
          )}
        </div>
      )}

      {/* Running status */}
      {!meta.final_complete && (
        <div className="mb-4 rounded-lg border border-edge bg-surface-2 px-4 py-2.5 text-center">
          <p className="text-[11px] text-slate-400">
            {meta.matches_complete} matches complete. Awards update live as results land.
          </p>
        </div>
      )}

      {/* Awards grid */}
      <div className="grid sm:grid-cols-2 gap-3">
        <AwardCard
          icon="⚽"
          title="Golden Boot"
          subtitle="Top scorer (goals, then assists, then fewest mins)"
          entries={data.golden_boot}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.player_name}</span>
              <span className="text-slate-500 text-[10px]">{e.team_name}</span>
              <span className="font-mono tabular-nums text-amber-400 font-bold w-16 text-right">
                {e.goals}G {e.assists}A
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🎯"
          title="Most Assists"
          subtitle="Playmaker of the tournament"
          entries={data.most_assists}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.player_name}</span>
              <span className="text-slate-500 text-[10px]">{e.team_name}</span>
              <span className="font-mono tabular-nums text-sky-400 font-bold w-16 text-right">
                {e.assists}A {e.goals}G
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🧤"
          title="Golden Glove"
          subtitle="Most saves (team-level)"
          entries={data.golden_glove}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">{e.games} games</span>
              <span className="font-mono tabular-nums text-emerald-400 font-bold w-12 text-right">
                {e.saves}
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🟨"
          title="Most Cards"
          subtitle="Discipline record (red = 3pts, yellow = 1pt)"
          entries={data.most_cards}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">{e.yellow_cards}Y {e.red_cards}R</span>
              <span className="font-mono tabular-nums text-rose-400 font-bold w-8 text-right">
                {e.card_points}
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🤝"
          title="Fair Play Award"
          subtitle="Fewest cards (min 3 matches)"
          entries={data.fair_play}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">{e.yellow_cards}Y {e.red_cards}R</span>
              <span className="font-mono tabular-nums text-emerald-400 font-bold w-8 text-right">
                {e.card_points}
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🏆"
          title="Best Team"
          subtitle="Points, then GD, then GF"
          entries={data.best_team}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <Flag url={e.flag_url} color={e.primary_color} />
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">{e.wins}W {e.draws}D {e.losses}L</span>
              <span className="font-mono tabular-nums text-amber-400 font-bold w-12 text-right">
                {e.points}pts
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🥅"
          title="Top Scoring Team"
          subtitle="Most goals scored"
          entries={data.top_scoring_team}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">{e.matches_played} games</span>
              <span className="font-mono tabular-nums text-sky-400 font-bold w-16 text-right">
                {e.goals_for} ({e.goals_per_game}/g)
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="😲"
          title="Biggest Upsets"
          subtitle="ELO gap: winner was rated lower"
          entries={data.biggest_upset}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <Link href={`/match/${e.match_id}`} className="flex-1 flex items-center gap-1 truncate">
                <span className="text-emerald-400 font-medium">{e.winner}</span>
                <span className="text-slate-600 text-[10px]">beat</span>
                <span className="text-rose-400">{e.loser}</span>
                <span className="text-slate-600 text-[10px] font-mono">{e.score}</span>
              </Link>
              <span className="font-mono tabular-nums text-amber-400 font-bold w-12 text-right">
                +{e.elo_gap}
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="🎬"
          title="Match of the Tournament"
          subtitle="Drama score: goals + pens + reds + upsets"
          entries={data.match_of_tournament}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <Link href={`/match/${e.match_id}`} className="flex-1 flex items-center gap-1 truncate">
                <span className="text-slate-200 font-medium">{e.home} v {e.away}</span>
                <span className="text-slate-600 text-[10px] font-mono">{e.score}</span>
                {e.went_to_pens && <span className="text-[9px] text-amber-400">PENS</span>}
              </Link>
              <span className="font-mono tabular-nums text-amber-400 font-bold w-8 text-right">
                {e.drama_score}
              </span>
            </Row>
          )}
        />

        <AwardCard
          icon="😞"
          title="Most Disappointing"
          subtitle="Highest-rated team that didn't reach QF"
          entries={data.most_disappointing}
          render={(e, i) => (
            <Row key={i} rank={i + 1} highlight={i === 0}>
              <Flag url={e.flag_url} color={e.primary_color} />
              <span className="flex-1 truncate text-slate-200 font-medium">{e.team_name}</span>
              <span className="text-slate-500 text-[10px]">ELO {e.elo?.toFixed(0)}</span>
              <span className="font-mono tabular-nums text-rose-400 font-bold w-12 text-right">
                {e.wins}W {e.matches_played}p
              </span>
            </Row>
          )}
        />
      </div>

      <p className="text-[10px] text-slate-600 mt-5 text-center leading-snug">
        All awards computed from the match archive. {meta.matches_complete} matches scored.
        {meta.final_complete
          ? " Final results — the 2026 World Cup is complete."
          : " Updated every 60 seconds."}
      </p>
    </div>
  )
}
