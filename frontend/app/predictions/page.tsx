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
      <div className="px-6 py-5">
        <p className="text-[12px] text-slate-500 mb-4 border border-[#1a2033] rounded-lg px-4 py-3 bg-[#0f1320]">
          The model only logs picks where it saw a genuine edge against bookmaker odds.
          Tracking them publicly proves the edge is real, not constructed in hindsight.
        </p>
        <TrackRecord stats={stats} />
        {stats.total > 0 && (
          <div className="flex justify-end mt-3 mb-2">
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
        <h2 className="text-[14px] font-bold mt-4 mb-3">All Predictions</h2>
        <HistoryTable entries={entries} />
      </div>
    </>
  )
}
