import Link from "next/link"
import { ArrowRight, Trophy } from "lucide-react"
import { KickoffCountdown } from "@/components/common/KickoffCountdown"
import type { Match, MatchPrediction, Market } from "@/lib/types"

interface TopPick {
  match_id: string
  match_label: string
  market_label: string
  ev: number
  bookmaker_odds: number
  model_prob: number
}

/**
 * Round-aware hero for knockout rounds. The "next match in 10h" is the single
 * most useful thing on the page for a knockout day, so it gets the top slot.
 *
 * Three things in one card:
 *   - Next-match strip:  countdown + flags + model 1X2 + venue + CTA
 *   - Top-pick strip:    the model's highest-EV bet across the whole round
 *   - Page anchor links: jump to the bracket, deep tournament projections
 *
 * Server-renders; the countdown ticks client-side via KickoffCountdown.
 */
function topModelPick(
  matches: (Match & { prediction?: MatchPrediction })[],
): TopPick | null {
  // Believability filters on the homepage hero pick. This is the FIRST thing
  // a casual visitor sees, so it must lean toward "boring value the model
  // likes" rather than the flashiest paper-EV number.
  //   1. EV > 5% — the same threshold the rest of the site uses.
  //   2. Model probability ≥ 35% — the bet has to be plausible on its own
  //      base rate, not just on the gap to the book.
  //   3. Bookmaker odds ≤ 5.0 — cuts longshots where a wide model/market gap
  //      inflates EV%.
  //   4. Mainline markets only — no double-chance (1x, x2, 12). A double-
  //      chance market sums two 1X2 outcomes, so any model/market disagreement
  //      on either of them comes through as inflated paper EV; the bet
  //      doesn't actually capture the disagreement, it just hides it.
  //   5. Reliability ≠ "longshot" if the backend has tagged it.
  // The picks page surfaces speculative + longshot picks behind their own
  // warnings; the hero takes the safest believable value bet of the round.
  const MAINLINE_MARKETS = new Set([
    "home_win", "draw", "away_win",
    "over_2_5", "under_2_5",
    "btts", "btts_no",
    "over_1_5", "under_3_5",
  ])
  let best: TopPick | null = null
  for (const m of matches) {
    if (!m.prediction) continue
    for (const mk of m.prediction.markets) {
      if (!MAINLINE_MARKETS.has(mk.market)) continue
      if (mk.ev <= 0.05) continue
      if (mk.our_prob < 0.35) continue
      if (mk.bookmaker_odds > 5.0) continue
      if (mk.reliability === "longshot") continue
      if (!best || mk.ev > best.ev) {
        best = {
          match_id: m.id,
          match_label: `${m.home.name} vs ${m.away.name}`,
          market_label: mk.label,
          ev: mk.ev,
          bookmaker_odds: mk.bookmaker_odds,
          model_prob: mk.our_prob,
        }
      }
    }
  }
  return best
}

function fmtKickoff(iso: string): string {
  // AU is the primary audience (owner is in Brisbane). Explicit IANA zone is
  // required on every toLocale* call in SSR — otherwise React #418 + the
  // string drifts to UTC at build time. See reference_au_timezone_skill memory.
  const d = new Date(iso)
  return d.toLocaleString("en-AU", {
    timeZone: "Australia/Brisbane",
    weekday: "short",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  })
}

export function NextUpHero({
  matches,
  roundLabel,
}: {
  matches: (Match & { prediction?: MatchPrediction })[]
  roundLabel: string
}) {
  const now = Date.now()
  const upcoming = matches
    .filter((m) => m.status === "upcoming" && new Date(m.kickoff).getTime() > now)
    .sort((a, b) => new Date(a.kickoff).getTime() - new Date(b.kickoff).getTime())

  // Prefer a live match if one is happening; otherwise the soonest upcoming.
  const liveMatch = matches.find((m) => m.status === "live") ?? null
  const next = liveMatch ?? upcoming[0] ?? null

  const pick = topModelPick(matches)

  if (!next && !pick) return null

  return (
    <section className="relative overflow-hidden rounded-3xl border border-edge shadow-e2 isolate">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(125%_120%_at_50%_-15%,#103a2c_0%,#0a1a18_42%,#07090e_100%)]" />
      <div
        className="absolute inset-0 -z-10 opacity-[0.05]"
        style={{ backgroundImage: "repeating-linear-gradient(102deg, transparent 0 64px, rgba(255,255,255,0.6) 64px 65px)" }}
      />
      <div className="absolute -top-28 left-1/3 w-[560px] h-[300px] rounded-full bg-emerald-500/20 blur-[110px] -z-10 pointer-events-none" />

      <div className="px-5 sm:px-9 py-7 sm:py-9">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-400/80">
          FIFA World Cup 2026 · {roundLabel}
        </p>

        {next && (
          <NextMatchBlock match={next} roundLabel={roundLabel} />
        )}

        {pick && (
          <TopPickBlock pick={pick} roundLabel={roundLabel} />
        )}

        <div className="mt-6 flex flex-wrap items-center gap-3">
          <Link
            href="/bracket"
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-[#06120c] font-semibold text-[14px] px-5 py-2.5 transition-colors"
          >
            <Trophy size={15} /> Full knockout bracket <ArrowRight size={16} />
          </Link>
          <Link
            href="/winner"
            className="inline-flex items-center gap-2 rounded-xl border border-edge hover:border-emerald-500/40 bg-surface-2/60 text-slate-300 font-semibold text-[13px] px-4 py-2.5 transition-colors"
          >
            Trophy projections <ArrowRight size={14} className="text-slate-500" />
          </Link>
        </div>
      </div>
    </section>
  )
}

function NextMatchBlock({
  match,
  roundLabel,
}: {
  match: Match & { prediction?: MatchPrediction }
  roundLabel: string
}) {
  const p = match.prediction
  const isLive = match.status === "live"
  return (
    <Link
      href={`/match/${match.id}?from=/`}
      className="mt-6 block rounded-2xl border border-edge bg-gradient-to-b from-surface-3/80 to-surface-2/40 p-5 hover:border-emerald-500/40 transition-colors group"
    >
      <div className="flex items-center gap-2 mb-3">
        {isLive ? (
          <span className="inline-flex items-center gap-1.5 text-[10px] font-black uppercase tracking-[0.18em] text-rose-300">
            <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-pulse" />
            Live now
          </span>
        ) : (
          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-emerald-400">
            Next up · {roundLabel}
          </span>
        )}
        <span className="text-slate-700">·</span>
        <span className="text-[11px] text-slate-500 truncate">
          {fmtKickoff(match.kickoff)} AEST · {match.venue}
        </span>
      </div>

      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="flex items-center gap-3 min-w-0">
          {match.home.flag_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={match.home.flag_url} alt="" className="w-12 h-9 rounded object-cover ring-1 ring-white/15 shadow shrink-0" />
          )}
          <div className="min-w-0">
            <p className="font-display font-bold text-[20px] sm:text-[22px] text-ink truncate leading-tight">{match.home.name}</p>
            {p && (
              <p className="text-emerald-400 font-bold text-[15px] tabular-nums leading-tight mt-0.5">
                {Math.round(p.home_win * 100)}%
              </p>
            )}
          </div>
        </div>

        <div className="text-center px-2">
          {isLive ? (
            <p className="text-[12px] font-black uppercase tracking-widest text-rose-300">Live</p>
          ) : (
            <>
              <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">Kick-off</p>
              <p className="text-[13px] sm:text-[14px] font-bold text-emerald-300 mt-0.5">
                <KickoffCountdown iso={match.kickoff} />
              </p>
            </>
          )}
        </div>

        <div className="flex items-center gap-3 min-w-0 justify-end">
          <div className="min-w-0 text-right">
            <p className="font-display font-bold text-[20px] sm:text-[22px] text-ink truncate leading-tight">{match.away.name}</p>
            {p && (
              <p className="text-orange-400 font-bold text-[15px] tabular-nums leading-tight mt-0.5">
                {Math.round(p.away_win * 100)}%
              </p>
            )}
          </div>
          {match.away.flag_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={match.away.flag_url} alt="" className="w-12 h-9 rounded object-cover ring-1 ring-white/15 shadow shrink-0" />
          )}
        </div>
      </div>

      <p className="text-[12px] text-slate-400 mt-3 group-hover:text-slate-200 transition-colors flex items-center gap-1">
        Open the full model read <ArrowRight size={12} />
      </p>
    </Link>
  )
}

function TopPickBlock({ pick, roundLabel }: { pick: TopPick; roundLabel: string }) {
  return (
    <Link
      href={`/match/${pick.match_id}?from=/`}
      className="mt-4 block rounded-2xl border border-emerald-500/20 bg-gradient-to-r from-emerald-950/40 via-emerald-900/10 to-surface-2/40 p-4 hover:border-emerald-500/40 transition-colors group"
    >
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10px] font-black uppercase tracking-[0.18em] text-emerald-300">
          Top model pick · {roundLabel}
        </span>
      </div>
      <p className="text-[15px] sm:text-[16px] text-ink font-bold leading-snug">
        {pick.market_label}
        <span className="text-slate-400 font-medium"> in </span>
        {pick.match_label}
      </p>
      <p className="text-[12px] text-slate-400 mt-1 tabular-nums">
        Model gives it <span className="text-slate-200 font-bold">{Math.round(pick.model_prob * 100)}%</span>
        <span className="text-slate-600"> · </span>
        Book is offering <span className="text-slate-200 font-bold">{pick.bookmaker_odds.toFixed(2)}</span>
        <span className="text-slate-600"> · </span>
        Edge <span className="text-emerald-300 font-bold">+{Math.round(pick.ev * 100)}%</span>
      </p>
      <p className="text-[11px] text-slate-500 mt-2 italic leading-snug">
        Highest edge among the round&apos;s mainline picks (model 35%+, odds &le; 5.0). Cross-check the match page before staking.
      </p>
    </Link>
  )
}
