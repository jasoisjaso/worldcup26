import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { BracketTree } from "@/components/bracket/BracketTree"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "World Cup 2026 Bracket Predictor: Projected Knockout Tree",
  description:
    "The projected 2026 FIFA World Cup knockout bracket from 20,000 Dixon-Coles simulations: the most likely teams to reach every round, from the last 32 to the final.",
  alternates: { canonical: "https://wc26.tinjak.com/bracket" },
}

export const dynamic = "force-dynamic"

export default async function BracketPage() {
  let data
  try {
    data = await api.tournament()
  } catch {
    data = null
  }

  return (
    <>
      <TopBar title="Projected Bracket" subtitle="The most likely knockout path, by simulation" />
      <div className="max-w-5xl mx-auto px-3 sm:px-5 py-5">
        {data?.bracket && data.teams.length > 0 ? (
          <BracketTree projection={data} />
        ) : (
          <p className="text-slate-500 text-sm py-16 text-center">
            The bracket is warming up. Refresh in a moment.
          </p>
        )}
      </div>
    </>
  )
}
