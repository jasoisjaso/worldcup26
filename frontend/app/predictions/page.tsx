import { TopBar } from "@/components/layout/TopBar"
import { TrackRecord } from "@/components/history/TrackRecord"
import { HistoryTable } from "@/components/history/HistoryTable"
import { ShareButton } from "@/components/common/ShareButton"
import { api } from "@/lib/api"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Prediction Track Record",
  description: "Every pre-kickoff pick logged automatically. Win/loss settled after results come in.",
}

export const dynamic = "force-dynamic"

export default async function PredictionsPage() {
  const [entries, stats] = await Promise.all([api.history(), api.historyStats()])

  return (
    <>
      <TopBar
        title="Prediction Track Record"
        subtitle="All picks logged before kickoff. Updated after each match settles."
      />
      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">
        <TrackRecord stats={stats} />
        <p className="text-[12px] text-slate-500 leading-relaxed mt-3">
          Every pick is logged before kickoff, only where the model sees a genuine edge against
          the bookmaker line, and settled after the result. No hindsight. <span className="text-slate-400">Closing
          Line Value (CLV)</span> compares the price the model flagged against the sharper price the
          market settles on just before kickoff. Beating that close, over many picks, is the clearest
          sign an edge is real, long before win rate or profit can prove it.
        </p>
        {stats.total > 0 && (
          <div className="flex justify-end mt-3">
            <ShareButton
              title="WC2026 Model Picks"
              text={[
                `WC2026 Predictor: ${stats.total} picks logged`,
                stats.correct > 0
                  ? `${stats.correct}/${stats.total} correct · ${Math.round(stats.accuracy * 100)}% accuracy · ${stats.roi >= 0 ? "+" : ""}${(stats.roi * 100).toFixed(1)}% ROI`
                  : `${stats.total} picks pending`,
              ].join("\n")}
              url="https://wc26.tinjak.com/predictions"
              label="Share track record"
            />
          </div>
        )}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mt-6 mb-2">Every pick</p>
        <HistoryTable entries={entries} />
      </div>
    </>
  )
}
