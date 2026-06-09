"use client"
import { useState } from "react"
import { Calendar, ChevronDown, ChevronUp, Plus } from "lucide-react"
import { TeamMeta } from "@/components/common/TeamMeta"
import { EVBadge } from "@/components/common/EVBadge"
import { ProbabilityBar } from "./ProbabilityBar"
import { WhyChips } from "./WhyChips"
import { MarketGrid } from "./MarketGrid"
import { ScoreGrid } from "./ScoreGrid"
import { kickoffLabel } from "@/lib/utils"
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
    ? "border-l-[3px] border-l-green-500"
    : ""

  return (
    <div className={`bg-[#0f1320] border border-[#1a2033] rounded-xl overflow-hidden mb-2.5 hover:border-[#243050] transition-colors ${borderClass}`}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#1a2033]">
        <div className="flex items-center gap-2.5">
          <span className="bg-[#1a2033] text-[10px] font-bold text-slate-500 rounded px-2 py-0.5 uppercase tracking-wide">
            Group {match.group}
          </span>
          <span className="flex items-center gap-1.5 text-[11px] text-slate-500">
            <Calendar size={11} />
            {kickoffLabel(match.kickoff)} · {match.venue}
          </span>
        </div>
        {topEv && <EVBadge ev={topEv.ev} label={topEv.label} />}
      </div>

      <div className="px-4 py-4">
        <div className="grid grid-cols-[1fr_48px_1fr] items-center gap-2">
          <TeamMeta team={match.home} align="left" />
          <p className="text-center text-[11px] text-slate-600 font-bold tracking-widest">VS</p>
          <TeamMeta team={match.away} align="right" />
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
            className="w-full flex items-center justify-between px-4 py-2 border-t border-[#1a2033] text-[11px] text-slate-500 hover:text-slate-300 hover:bg-[#141929] transition-colors"
          >
            <span>Why this pick · Markets · Scores</span>
            {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>

          {expanded && (
            <div className="px-4 pb-4 space-y-4 border-t border-[#1a2033]">
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

              <div className="flex gap-2 pt-1">
                {topEv && onAddToAcca && (
                  <button
                    onClick={() => onAddToAcca(match.id, topEv.market)}
                    className="flex items-center gap-1.5 bg-blue-600 hover:bg-blue-500 text-white text-[12px] font-semibold px-3 py-1.5 rounded-lg transition-colors"
                  >
                    <Plus size={13} />
                    Add {topEv.label} to Acca
                  </button>
                )}
                <button className="flex items-center gap-1.5 bg-[#141929] border border-[#1a2033] text-slate-400 text-[12px] font-semibold px-3 py-1.5 rounded-lg hover:text-slate-200 transition-colors">
                  Build SGM
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
