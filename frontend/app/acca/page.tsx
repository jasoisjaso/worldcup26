import { TopBar } from "@/components/layout/TopBar"

export default function AccaPage() {
  return (
    <>
      <TopBar title="Acca Builder" subtitle="Build and optimise your accumulator" />
      <div className="px-6 py-5 text-slate-500 text-sm">Select matches from the Matches page to add legs here.</div>
    </>
  )
}
