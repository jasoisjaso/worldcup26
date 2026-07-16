import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { AwardsClient } from "@/components/awards/AwardsClient"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "World Cup 2026 Awards: Golden Boot, Best Team & More",
  description:
    "Tournament awards computed from the live match archive: Golden Boot, Most Assists, Golden Glove, Fair Play, Biggest Upsets, Match of the Tournament and more.",
  alternates: { canonical: "https://wc26.tinjak.com/awards" },
}

export const dynamic = "force-dynamic"

export default async function AwardsPage() {
  let data = null
  try {
    data = await api.awards()
  } catch {
    /* render empty state */
  }

  const champion = data?._meta?.champion
  const subtitle = data?._meta?.final_complete
    ? `${champion?.name ?? ""} crowned champions`
    : `${data?._meta?.matches_complete ?? 0} matches complete`

  return (
    <>
      <TopBar title="Tournament Awards" subtitle={subtitle} />
      {data ? (
        <AwardsClient initialData={data} />
      ) : (
        <div className="max-w-3xl mx-auto px-3 sm:px-5 py-16 text-center">
          <p className="text-slate-500 text-sm">
            Awards populate as matches are played. Check back after the first results land.
          </p>
        </div>
      )}
    </>
  )
}
