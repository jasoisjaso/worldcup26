import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { LiveHub } from "@/components/live/LiveHub"
import { api } from "@/lib/api"
import { NotificationBell } from "@/components/common/NotificationBell"

export const metadata: Metadata = {
  title: "Live Matches",
  description: "Live World Cup 2026 matches — scores, win probability, stats, golden boot, value picks. Updated live.",
}

export const dynamic = "force-dynamic"

export default async function LivePage() {
  let hub: any = null
  let upcoming: any = null
  let completed: any = null
  let topscores: any = null
  try {
    ;[hub, upcoming, completed, topscores] = await Promise.all([
      api.liveHub(),
      api.upcoming().catch(() => null),
      api.recent().catch(() => null),
      api.scorers().catch(() => null),
    ])
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
      <LiveHub initialData={hub} upcoming={upcoming} completed={completed} topscores={topscores} />
    </>
  )
}
