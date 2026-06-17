import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { WinnerBoard } from "@/components/tournament/WinnerBoard"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "Who Wins the World Cup? Tournament Projections",
  description:
    "Monte-Carlo projections for the 2026 FIFA World Cup: each nation's chance of topping its group, reaching the knockouts, and going all the way, simulated from the Dixon-Coles model.",
  alternates: { canonical: "https://wc26.tinjak.com/winner" },
}

// Always render fresh from the (server-cached) projection; never prerender an empty
// build-time snapshot when the backend isn't reachable during the image build.
export const dynamic = "force-dynamic"

export default async function WinnerPage() {
  let data
  try {
    data = await api.tournament()
  } catch {
    data = null
  }

  return (
    <>
      <TopBar title="World Cup Projections" subtitle="Who advances, who wins, by simulation" />
      {data && data.teams.length > 0 ? (
        <>
          <div className="px-4 pt-4">
            <a
              href="/bracket"
              className="flex items-center justify-between gap-3 rounded-xl border border-edge bg-surface-2 hover:border-emerald-500/40 shadow-e1 px-4 py-3 transition-colors group"
            >
              <span className="text-[13px] text-slate-300">
                <span className="font-semibold text-white">See the projected bracket</span>
                <span className="text-slate-500"> — the knockout path from these same simulations</span>
              </span>
              <span className="text-emerald-400 text-[18px] group-hover:translate-x-0.5 transition-transform">→</span>
            </a>
          </div>
          <WinnerBoard data={data} />
        </>
      ) : (
        <p className="text-slate-500 text-sm py-16 text-center px-4">
          Projections are warming up. Refresh in a moment.
        </p>
      )}
    </>
  )
}
