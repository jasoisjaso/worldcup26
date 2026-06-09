import { TopBar } from "@/components/layout/TopBar"
import { TrackRecord } from "@/components/history/TrackRecord"
import { HistoryTable } from "@/components/history/HistoryTable"
import { api } from "@/lib/api"

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
          We only record picks where the model found genuine edge against bookmaker odds.
          Tracking this publicly proves whether the edge is real, not just hindsight.
        </p>
        <TrackRecord stats={stats} />
        <h2 className="text-[14px] font-bold mt-6 mb-3">All Predictions</h2>
        <HistoryTable entries={entries} />
      </div>
    </>
  )
}
