import { Zap } from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import type { Match3Alert } from "@/lib/types"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Match 3 Watch",
  description: "Matchday 3 group games where rotation or must-win pressure changes the result.",
}

function AlertCard({ alert }: { alert: Match3Alert }) {
  return (
    <div className="bg-surface-2 border border-amber-900/40 border-l-[3px] border-l-amber-500 rounded-xl px-4 py-3 mb-2.5">
      <div className="flex items-start gap-2.5">
        <Zap size={15} className="text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="bg-edge rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-slate-500">
              Group {alert.group}
            </span>
            <span className="text-[12px] font-bold text-white">{alert.match_label}</span>
          </div>
          <p className="text-[12px] text-amber-400 font-semibold mt-1">
            {alert.rotation_team} is {alert.rotation_status}
          </p>
          <p className="text-[11px] text-slate-400 mt-0.5 leading-relaxed">
            {alert.warning}
          </p>
          <p className="text-[11px] text-slate-500 mt-1.5">
            Backing the team that still needs a result in Match 3 returned{" "}
            <strong className="text-slate-300">+12.8% ROI</strong> over the last two World Cups.
            Bookmakers set those odds before qualification status was known.
          </p>
        </div>
      </div>
    </div>
  )
}

export default async function Match3Page() {
  let alerts: Match3Alert[] = []
  try {
    alerts = await api.match3()
  } catch {
    alerts = []
  }

  return (
    <>
      <TopBar
        title="Match 3 Watch"
        subtitle="Matchday 3 fixtures where qualification status may not yet be in the odds"
      />

      <div className="px-4 py-4">
        <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3 mb-4 text-[12px] text-slate-400 leading-relaxed">
          When a team qualifies or gets eliminated before their final group game, they often
          rotate their squad. Bookmakers are typically slow to adjust. The team that still
          needs a result becomes a strong statistical bet.
        </div>

        {alerts.length === 0 ? (
          <div className="text-center py-12">
            <Zap size={28} className="mx-auto mb-3 text-slate-700" />
            <p className="text-slate-400 text-[14px] font-semibold">No rotation alerts yet</p>
            <p className="text-slate-600 text-[12px] mt-1 max-w-xs mx-auto">
              Alerts appear here once matchday 1 and 2 results are recorded and any
              team qualifies or is eliminated before their final group game.
            </p>
          </div>
        ) : (
          <div>
            {alerts.map((alert) => (
              <AlertCard key={alert.match_id} alert={alert} />
            ))}
          </div>
        )}
      </div>
    </>
  )
}
