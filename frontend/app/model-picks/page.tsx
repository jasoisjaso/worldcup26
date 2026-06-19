import { TopBar } from "@/components/layout/TopBar"
import { ModelPicksClient } from "@/components/picks/ModelPicksClient"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Model picks: daily auto-picked multis",
  description: "Daily model-picked multi bets. Balanced edges across same-game and cross-match combos, self-scored with a public running ROI.",
}

export const dynamic = "force-dynamic"  // always fresh

async function fetchData() {
  try {
    const backend = process.env.BACKEND_URL ?? "http://wc26-backend:8000"
    const r = await fetch(`${backend}/picks/model-multis`, { cache: "no-store" })
    return r.json()
  } catch {
    return { active: [], recent: [], stats: { total_settled: 0, won: 0, lost: 0, hit_rate_pct: null, profit_loss_units: 0, roi_pct: null } }
  }
}

export default async function ModelPicksPage() {
  const data = await fetchData()
  return (
    <>
      <TopBar title="Model picks" subtitle="Daily auto-curated multis the model thinks have edge" />
      <div className="px-3 sm:px-5 pt-4 pb-8 max-w-5xl mx-auto">
        <ModelPicksClient initialData={data} />
      </div>
    </>
  )
}
