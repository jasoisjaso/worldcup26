import { TopBar } from "@/components/layout/TopBar"
import { MyPicksClient } from "@/components/picks/MyPicksClient"
import { api } from "@/lib/api"
import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "My picks vs the model",
  description: "Track your own predictions side-by-side with the model. Local-only, no sign-up.",
}

export const dynamic = "force-dynamic"

export default async function MyPicksPage() {
  const matches = await api.matches().catch(() => [])
  return (
    <>
      <TopBar title="My picks vs the model" subtitle="Saved on this device. No sign-up." />
      <div className="px-3 sm:px-5 pt-4 pb-8 max-w-3xl mx-auto">
        <MyPicksClient matches={matches} />
      </div>
    </>
  )
}
