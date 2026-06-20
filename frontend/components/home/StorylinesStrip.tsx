import Link from "next/link"
import { Flame, Goal, Sparkles, Radio } from "lucide-react"

interface Card {
  kind: "upset" | "goalfest" | "player_haul" | "live_now"
  match_id: string
  title: string
  headline: string
  score?: string
  gap?: number
  total_goals?: number
  elapsed_min?: number
  player_id?: number
  team_name?: string
  goals?: number
}

const ICONS: Record<string, typeof Flame> = {
  upset: Flame,
  goalfest: Goal,
  player_haul: Sparkles,
  live_now: Radio,
}

const TINTS: Record<string, string> = {
  upset: "border-rose-500/30 from-rose-950/40 to-surface-2 text-rose-300",
  goalfest: "border-amber-500/30 from-amber-950/40 to-surface-2 text-amber-300",
  player_haul: "border-emerald-500/30 from-emerald-950/40 to-surface-2 text-emerald-300",
  live_now: "border-rose-500/40 from-rose-900/50 to-surface-2 text-rose-200",
}

// Three drama cards for the homepage: today's biggest upset, the highest-scoring
// match, and the player of the day. Auto-hides when nothing today is dramatic.
// All read straight off our existing DB — no API cost.
export function StorylinesStrip({ cards }: { cards: Card[] }) {
  if (!cards.length) return null
  return (
    <div className="mb-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Today on the pitch</p>
      <div className="flex gap-2 overflow-x-auto pb-1 -mx-3 px-3 sm:mx-0 sm:px-0">
        {cards.map((c, i) => {
          const Icon = ICONS[c.kind]
          const tint = TINTS[c.kind]
          const href = c.kind === "player_haul" && c.player_id
            ? `/player/${c.player_id}?from=/`
            : `/match/${c.match_id}?from=/`
          return (
            <Link
              key={i}
              href={href}
              className={`shrink-0 w-[260px] sm:w-[300px] rounded-2xl border bg-gradient-to-br ${tint} shadow-e1 p-3.5 hover:shadow-e2 transition-shadow`}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Icon size={13} strokeWidth={2.4} className="opacity-80 shrink-0" />
                <p className="text-[10px] font-bold uppercase tracking-wider opacity-80">{c.title}</p>
              </div>
              <p className="text-[14px] font-bold text-white leading-snug">{c.headline}</p>
              <p className="text-[11px] text-slate-400 mt-1 font-mono tabular-nums">
                {c.score && c.kind === "upset" && <>FT {c.score} · {c.gap} ELO underdog</>}
                {c.total_goals != null && c.kind === "goalfest" && <>{c.total_goals} goals · full time</>}
                {c.team_name && c.kind === "player_haul" && <>{c.team_name} · {c.goals} goals</>}
                {c.kind === "live_now" && (
                  <span className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-pulse" />
                    {c.elapsed_min}&apos; · in play
                  </span>
                )}
              </p>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
