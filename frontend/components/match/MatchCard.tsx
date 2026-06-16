"use client"
import { useState } from "react"
import Link from "next/link"
import { Calendar, ChevronDown, ChevronUp, Plus, Triangle, CreditCard, ArrowRight } from "lucide-react"
import { TeamMeta } from "@/components/common/TeamMeta"
import { ProbabilityBar } from "./ProbabilityBar"
import { WhyChips } from "./WhyChips"
import { MarketGrid } from "./MarketGrid"
import { ScoreGrid } from "./ScoreGrid"
import { KickoffTime } from "@/components/common/KickoffTime"
import { BroadcastBadge } from "@/components/common/BroadcastBadge"
import type { Match, MatchPrediction } from "@/lib/types"

interface MatchCardProps {
  match: Match
  prediction?: MatchPrediction
  onAddToAcca?: (matchId: string, market: string) => void
}

export function MatchCard({ match, prediction, onAddToAcca }: MatchCardProps) {
  const [expanded, setExpanded] = useState(false)

  const topEv = prediction?.markets
    .filter((m) => m.is_positive_ev)
    .sort((a, b) => b.ev - a.ev)[0]

  const borderClass = topEv && topEv.ev > 0.05
    ? "border-l-[3px] border-l-amber-500"
    : ""

  return (
    <div
      style={{ borderLeftColor: match.home.primary_color || "#ffb000", borderLeftWidth: 3 }}
      className={`bg-gradient-to-b from-surface-3 to-surface-2 border border-edge rounded-card shadow-e1 overflow-hidden mb-3 hover:border-edge-strong hover:shadow-e2 hover:-translate-y-0.5 transition-all duration-150 ${borderClass}`}
    >
      {/* Match header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-edge gap-2">
        <div className="flex items-center gap-2 min-w-0 overflow-hidden">
          <span className="shrink-0 bg-edge text-[10px] font-bold text-slate-500 rounded px-2 py-0.5 uppercase tracking-wide">
            Group {match.group}
          </span>
          <span className="flex items-center gap-1 text-[11px] text-slate-600 min-w-0 overflow-hidden">
            <Calendar size={11} className="shrink-0" />
            <KickoffTime iso={match.kickoff} />
            <span className="text-slate-700 shrink-0">·</span>
            <span className="truncate">{match.venue}</span>
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <BroadcastBadge />
          {topEv && topEv.ev > 0.05 && (
            <span className="text-[10px] font-bold text-amber-400 bg-amber-950/50 border border-amber-900/60 rounded px-2 py-0.5">
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
              <p className="text-[30px] sm:text-[34px] font-display font-bold text-amber-400 leading-none mt-2 tabular-nums">
                {Math.round(prediction.home_win * 100)}%
              </p>
            )}
          </div>

          {/* VS + draw / actual score */}
          <div className="flex flex-col items-center pt-1 px-1">
            {match.status === "complete" && match.actual_score != null ? (
              <>
                <p className="text-[9px] text-slate-600 font-bold uppercase tracking-widest">FT</p>
                <p className="text-[20px] font-black text-white tabular-nums leading-tight mt-0.5 whitespace-nowrap">
                  {match.actual_score.home}&ndash;{match.actual_score.away}
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
      </div>

      {prediction && (
        <>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="w-full flex items-center justify-between px-4 py-2 border-t border-edge text-[11px] text-slate-500 hover:text-slate-300 hover:bg-surface-3 transition-colors"
          >
            <span>Analysis · Markets · Scores</span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {expanded && (
            <div className="px-4 pb-4 space-y-4 border-t border-edge">
              {prediction.why_factors.length > 0 && (
                <div>
                  <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2 mt-3">
                    Why this pick
                  </p>
                  <WhyChips factors={prediction.why_factors} />
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

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {topEv && onAddToAcca && (
                  <button
                    onClick={() => onAddToAcca(match.id, topEv.market)}
                    className="flex items-center gap-1.5 bg-amber-700 hover:bg-amber-600 text-white text-[12px] font-semibold px-3 py-1.5 rounded-lg transition-colors"
                  >
                    <Plus size={13} />
                    Add {topEv.label} to Acca
                  </button>
                )}
                <Link
                  href={`/match/${match.id}`}
                  className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-400 hover:text-amber-300 px-3 py-1.5 rounded-lg border border-amber-900/50 hover:border-amber-700 transition-colors"
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
