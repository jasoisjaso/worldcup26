import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { LiveHub } from "@/components/live/LiveHub"
import { api } from "@/lib/api"
import { NotificationBell } from "@/components/common/NotificationBell"

export const metadata: Metadata = {
  title: "Live Matches",
  description: "Live World Cup 2026 matches — scores, win probability, stats. Updated every 30 seconds.",
}

export const dynamic = "force-dynamic"

export default async function LivePage() {
  let hub: any = null
  try {
    hub = await api.liveHub()
  } catch {
    hub = null
  }

  return (
    <>
      <TopBar
        title="Live"
        subtitle={hub ? `${hub.live_count} match${hub.live_count === 1 ? "" : "es"} in play` : "Check back when matches kick off"}
        action={<NotificationBell />}
      />
      <LiveHub initialData={hub} />
    </>
  )
}
