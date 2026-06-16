import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { WinnerBoard } from "@/components/tournament/WinnerBoard"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "Who Wins the World Cup? — Tournament Projections",
  description:
    "Monte-Carlo projections for the 2026 FIFA World Cup: each nation's chance of topping its group, reaching the knockouts, and going all the way — simulated from the Dixon-Coles model.",
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
      <TopBar title="World Cup Projections" subtitle="Who advances, who wins — by simulation" />
      {data && data.teams.length > 0 ? (
        <WinnerBoard data={data} />
      ) : (
        <p className="text-slate-500 text-sm py-16 text-center px-4">
          Projections are warming up. Refresh in a moment.
        </p>
      )}
    </>
  )
}
