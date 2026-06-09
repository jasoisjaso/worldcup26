import { TopBar } from "@/components/layout/TopBar"

export default function Match3Page() {
  return (
    <>
      <TopBar title="Match 3 Watch" subtitle="Teams where qualification status may affect team selection" />
      <div className="px-6 py-5 text-slate-500 text-sm">Alerts appear here once group stage standings are known.</div>
    </>
  )
}
