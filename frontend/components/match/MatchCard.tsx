"use client"
import { useState } from "react"
import Link from "next/link"
import { Calendar, ChevronDown, ChevronUp, Plus, Triangle, CreditCard, ArrowRight } from "lucide-react"
import { TeamMeta } from "@/components/common/TeamMeta"
import { LiveScoreLive } from "@/components/common/LiveScoreLive"
import { FollowBell } from "./FollowBell"
import { getCachedEndpoint } from "@/lib/push"
import { ProbabilityBar } from "./ProbabilityBar"
import { FactorContributions } from "./FactorContributions"
import { MarketGrid } from "./MarketGrid"
import { ScoreGrid } from "./ScoreGrid"
import { KickoffTime } from "@/components/common/KickoffTime"
import { BroadcastBadge } from "@/components/common/BroadcastBadge"
import type { Match, MatchPrediction, TeamHarvestedSnapshot } from "@/lib/types"
import { ConfidenceChip, confidenceFromProbs } from "@/components/common/ConfidenceChip"
import { roundForMatchday } from "@/lib/rounds"

interface MatchCardProps {
  match: Match
  prediction?: MatchPrediction
  onAddToAcca?: (matchId: string, market: string) => void
  /** Source page path — passed through to /match/<id>?from=<from> so the detail page's
   * back button returns here instead of defaulting to /. */
  from?: string
}

export function MatchCard({ match, prediction, onAddToAcca, from }: MatchCardProps) {
  const matchHref = from ? `/match/${match.id}?from=${encodeURIComponent(from)}` : `/match/${match.id}`
  const [expanded, setExpanded] = useState(false)

  const topEv = prediction?.markets
    .filter((m) => m.is_positive_ev)
    .sort((a, b) => b.ev - a.ev)[0]

  const borderClass = topEv && topEv.ev > 0.05
    ? "border-l-[3px] border-l-emerald-500"
    : ""

  return (
    <div className={`bg-gradient-to-b from-surface-3 to-surface-2 border border-edge rounded-xl shadow-e1 overflow-hidden mb-3 hover:border-edge-strong hover:shadow-e2 hover:-translate-y-0.5 transition-all duration-150 ${borderClass}`}>
      {/* Match header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-edge gap-2">
        <div className="flex items-center gap-2 min-w-0 overflow-hidden">
          <span className="shrink-0 bg-edge text-[10px] font-bold text-slate-500 rounded px-2 py-0.5 uppercase tracking-wide">
            {match.group ? `Group ${match.group}` : roundForMatchday(match.matchday).label}
          </span>
          <span className="flex items-center gap-1 text-[11px] text-slate-600 min-w-0 overflow-hidden">
            <Calendar size={11} className="shrink-0" />
            <KickoffTime iso={match.kickoff} />
            <span className="text-slate-700 shrink-0">·</span>
            <span className="truncate">{match.venue}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <FollowBell matchId={match.id} />
          <BroadcastBadge />
          {topEv && topEv.ev > 0.05 && (
            <span className="text-[10px] font-bold text-emerald-400 bg-emerald-950/50 border border-emerald-900/60 rounded px-2 py-0.5">
              Value
            </span>
          )}
        </div>
      </div>

      {/* Teams + probabilities */}
      <div className="px-4 py-4">
        <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-2">
          {/* Home team */}
          <div>
            <TeamMeta team={match.home} align="left" />
            {prediction && (
              <p className="text-[30px] sm:text-[34px] font-display font-bold text-emerald-400 leading-none mt-2 tabular-nums">
                {Math.round(prediction.home_win * 100)}%
              </p>
            )}
          </div>

          {/* VS + draw / actual score / interruption pill.
              Interruption pill takes priority over everything else — it's
              the one signal users MUST see if the match isn't following
              the normal arc. Pre 2026-06-23 a weather-suspended FRA-IRQ
              showed "FT 1-0" here, which was wrong and the trigger for
              the whole interruption batch. */}
          <div className="flex flex-col items-center pt-1 px-1">
            {match.interruption_status ? (
              <InterruptionPill
                status={match.interruption_status}
                partial={match.partial_score ?? null}
                reason={match.interruption_reason ?? null}
              />
            ) : match.status === "live" && match.live ? (
              <LiveScoreLive matchId={match.id} initial={match.live} variant="card" />
            ) : match.status === "complete" && match.actual_score != null ? (
              <>
                <p className="text-[9px] text-slate-600 font-bold uppercase tracking-widest">FT</p>
                <p className="text-[20px] font-black text-white tabular-nums leading-tight mt-0.5 whitespace-nowrap">
                  {match.actual_score.home}-{match.actual_score.away}
                </p>
              </>
            ) : (
              <>
                <p className="text-[10px] text-slate-700 font-bold tracking-widest">VS</p>
                {prediction && (
                  <>
                    <p className="text-[13px] font-bold text-slate-500 tabular-nums leading-tight mt-1.5">
                      {Math.round(prediction.draw * 100)}%
                    </p>
                    <p className="text-[8px] text-slate-700 uppercase tracking-wide">draw</p>
                  </>
                )}
              </>
            )}
          </div>

          {/* Away team */}
          <div className="text-right">
            <TeamMeta team={match.away} align="right" />
            {prediction && (
              <p className="text-[30px] sm:text-[34px] font-display font-bold text-orange-400 leading-none mt-2 tabular-nums">
                {Math.round(prediction.away_win * 100)}%
              </p>
            )}
          </div>
        </div>

        {prediction && (
          <ProbabilityBar
            homeWin={prediction.home_win}
            draw={prediction.draw}
            awayWin={prediction.away_win}
            homeLabel={`${match.home.name} Win`}
            awayLabel={`${match.away.name} Win`}
          />
        )}

        {topEv && topEv.ev > 0.05 && (
          <div className="mt-3 flex items-center gap-2 rounded-lg border border-emerald-500/25 bg-emerald-950/30 px-3 py-2">
            <span className="text-[9px] font-black uppercase tracking-widest text-emerald-300 shrink-0">
              Model pick
            </span>
            <span className="text-[12px] text-slate-200 font-bold truncate">{topEv.label}</span>
            <span className="text-slate-700 shrink-0">·</span>
            <span className="text-[12px] text-slate-400 tabular-nums shrink-0">
              {topEv.bookmaker_odds.toFixed(2)}
            </span>
            <span className="ml-auto text-[12px] font-bold text-emerald-300 tabular-nums shrink-0">
              +{Math.round(topEv.ev * 100)}%
            </span>
          </div>
        )}
      </div>

      {prediction && (
        <>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="w-full flex items-center justify-between gap-2 px-4 py-2 border-t border-edge text-[11px] text-slate-500 hover:text-slate-300 hover:bg-surface-3 transition-colors"
          >
            <span className="flex items-center gap-2">
              <span>Analysis · Markets · Scores</span>
              <ConfidenceChip
                level={confidenceFromProbs(prediction.home_win, prediction.draw, prediction.away_win)}
                compact
              />
            </span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {expanded && (
            <div className="px-4 pb-4 space-y-4 border-t border-edge">
              {(prediction.why_factors.length > 0 || prediction.context) && (
                <div className="mt-3">
                  <FactorContributions
                    context={prediction.context}
                    factors={prediction.why_factors}
                  />
                </div>
              )}

              <div>
                <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
                  Market breakdown
                </p>
                <MarketGrid markets={prediction.markets} />
              </div>

              <div>
                <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
                  Most likely scores
                </p>
                <ScoreGrid scores={prediction.top_scores} />
              </div>

              {(prediction.expected_corners != null || prediction.expected_cards != null) && (
                <div>
                  <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
                    Set pieces
                  </p>
                  <div className="flex gap-2">
                    {prediction.expected_corners != null && (
                      <div className="bg-surface-2 rounded-lg px-3 py-2.5 border border-edge flex-1">
                        <div className="flex items-center gap-1.5 mb-1">
                          <Triangle size={10} className="text-slate-500" />
                          <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Corners</span>
                        </div>
                        <p className="text-[20px] font-extrabold text-slate-100 leading-none">
                          {prediction.expected_corners.toFixed(1)}
                        </p>
                        <p className="text-[10px] text-slate-600 mt-1">model total</p>
                      </div>
                    )}
                    {prediction.expected_cards != null && (
                      <div className="bg-surface-2 rounded-lg px-3 py-2.5 border border-edge flex-1">
                        <div className="flex items-center gap-1.5 mb-1">
                          <CreditCard size={10} className="text-slate-500" />
                          <span className="text-[10px] text-slate-500 font-semibold uppercase tracking-wide">Yellow cards</span>
                        </div>
                        <p className="text-[20px] font-extrabold text-slate-100 leading-none">
                          {prediction.expected_cards.toFixed(1)}
                        </p>
                        <p className="text-[10px] text-slate-600 mt-1">model total</p>
                      </div>
                    )}
                  </div>
                  <p className="text-[10px] text-slate-700 mt-2">Model estimates only. No live corner or card data.</p>
                </div>
              )}

              <HarvestedStrip
                home={prediction.context?.harvested?.home ?? null}
                away={prediction.context?.harvested?.away ?? null}
                homeName={match.home.name}
                awayName={match.away.name}
              />

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {topEv && onAddToAcca && (
                  <button
                    onClick={() => {
                      onAddToAcca(match.id, topEv.market)
                      // Bookmaker-pattern auto-follow (industry standard:
                      // bet365 does this). Fire-and-forget — if there's
                      // no push endpoint cached we silently skip; we don't
                      // pop a permission prompt for an implicit action.
                      // The backend's no_auto_refollow flag prevents this
                      // from re-subscribing a user who explicitly unfollowed.
                      const ep = getCachedEndpoint()
                      if (ep) {
                        fetch("/api/push/follow-match", {
                          method: "POST",
                          headers: { "Content-Type": "application/json" },
                          body: JSON.stringify({
                            endpoint: ep,
                            match_id: match.id,
                            source: "auto_pick",
                          }),
                        }).catch(() => { /* never block the acca flow */ })
                      }
                    }}
                    className="flex items-center gap-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-[12px] font-semibold px-3 py-1.5 rounded-lg transition-colors"
                  >
                    <Plus size={13} />
                    Add {topEv.label} to Acca
                  </button>
                )}
                <Link
                  href={matchHref}
                  className="flex items-center gap-1.5 text-[12px] font-semibold text-emerald-400 hover:text-emerald-300 px-3 py-1.5 rounded-lg border border-emerald-900/50 hover:border-emerald-700 transition-colors"
                >
                  All 30+ markets &amp; fair odds
                  <ArrowRight size={13} />
                </Link>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}

/** Centre-of-card pill shown when match.interruption_status is set. Replaces
 *  the FT score for delayed/postponed/abandoned matches so the user never sees
 *  a phantom final score on a paused fixture. 'awarded' (off-pitch decision)
 *  shows the awarded score with a small flag so the standings story still
 *  makes sense even though picks are voided per industry rule. */
function InterruptionPill({
  status,
  partial,
  reason,
}: {
  status: "delayed" | "postponed" | "abandoned" | "awarded"
  partial: { home: number; away: number } | null
  reason: string | null
}) {
  // Visual treatment ordered by severity. Delayed = match is paused,
  // could still finish today (FIFA's posture). Postponed = won't play
  // today. Abandoned = match is over, partial result is final-as-record
  // but picks void. Awarded = off-pitch ruling stands.
  const config = {
    delayed: { label: "Delayed", glyph: "⏸", color: "amber", note: "Paused, waiting for restart" },
    postponed: { label: "Postponed", glyph: "↺", color: "slate", note: "Rescheduling" },
    abandoned: { label: "Abandoned", glyph: "✕", color: "rose", note: "Picks voided" },
    awarded: { label: "Awarded", glyph: "⚖", color: "slate", note: "Off-pitch ruling" },
  }[status]

  const colorMap: Record<string, string> = {
    amber: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    slate: "bg-slate-500/15 text-slate-300 border-slate-500/30",
    rose: "bg-rose-500/15 text-rose-300 border-rose-500/30",
  }

  return (
    <div className="flex flex-col items-center">
      <span
        className={`inline-flex items-center gap-1 text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${colorMap[config.color]}`}
        // Never leak the internal feed marker ("api-football status=PST" /
        // "watchdog: ...") into the hover tooltip — fall back to the note.
        title={
          reason && !reason.startsWith("api-football status=") && !reason.startsWith("watchdog:")
            ? reason
            : config.note
        }
      >
        <span aria-hidden>{config.glyph}</span>
        {config.label}
      </span>
      {partial != null && (
        <p className="text-[13px] font-bold text-slate-300 tabular-nums leading-tight mt-1 whitespace-nowrap">
          {partial.home}-{partial.away}
        </p>
      )}
      <p className="text-[9px] text-slate-600 mt-0.5 text-center max-w-[110px] leading-tight">
        {config.note}
      </p>
    </div>
  )
}


/** Compact strip of REAL harvested numbers (rolling xG, corners, trend) per team.
 *  Renders nothing until at least one side has archived fixtures — so it stays
 *  invisible early in the tournament and lights up as group games get harvested. */
function HarvestedStrip({
  home, away, homeName, awayName,
}: {
  home: TeamHarvestedSnapshot | null
  away: TeamHarvestedSnapshot | null
  homeName: string
  awayName: string
}) {
  if (!home && !away) return null

  const trendGlyph = (t?: string) =>
    t === "rising" ? "▲" : t === "falling" ? "▼" : t === "flat" ? "▬" : ""
  const trendColor = (t?: string) =>
    t === "rising" ? "text-emerald-400" : t === "falling" ? "text-orange-400" : "text-slate-500"

  const row = (label: string, snap: TeamHarvestedSnapshot | null, accent: string) => (
    <div className="flex-1 bg-surface-2 rounded-lg px-3 py-2.5 border border-edge">
      <p className={`text-[10px] font-semibold truncate ${accent}`}>{label}</p>
      {snap ? (
        <div className="mt-1.5 space-y-1">
          {snap.xg_per_match != null && (
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500">xG / match</span>
              <span className="tabular-nums text-slate-100 font-semibold">
                {snap.xg_per_match.toFixed(2)}
                {snap.xg_trend && (
                  <span className={`ml-1 ${trendColor(snap.xg_trend)}`}>{trendGlyph(snap.xg_trend)}</span>
                )}
              </span>
            </div>
          )}
          {snap.corners_per_match != null && (
            <div className="flex items-center justify-between text-[11px]">
              <span className="text-slate-500">Corners / match</span>
              <span className="tabular-nums text-slate-100 font-semibold">{snap.corners_per_match.toFixed(1)}</span>
            </div>
          )}
          {snap.xg_sample != null && (
            <p className="text-[9px] text-slate-600">from last {snap.xg_sample} archived matches</p>
          )}
        </div>
      ) : (
        <p className="text-[10px] text-slate-600 mt-1.5">No archived matches yet</p>
      )}
    </div>
  )

  return (
    <div>
      <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
        Recent data <span className="text-emerald-600/70 normal-case tracking-normal">· harvested</span>
      </p>
      <div className="flex gap-2">
        {row(homeName, home, "text-emerald-400")}
        {row(awayName, away, "text-orange-400")}
      </div>
    </div>
  )
}
