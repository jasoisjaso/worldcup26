import { NextResponse } from "next/server"

// Same-origin proxy for the LiveTicker client poller. Backend lives on a
// docker-internal hostname not reachable from the browser; this route forwards.
//
// Cached 10s at the edge: every open tab polls this endpoint on a loop, so
// without a tiny SWR window every poll wakes the FastAPI scoreboard query. 10s
// is below the live-poll interval (30s) so freshness is preserved, while
// concurrent viewers collapse onto one backend hit per window.
export const dynamic = "force-dynamic"

export async function GET() {
  const base = process.env.BACKEND_URL ?? "http://wc26-backend:8000"
  try {
    const r = await fetch(`${base}/live/summary`, { next: { revalidate: 10 } })
    const body = await r.text()
    return new NextResponse(body, {
      status: r.status,
      headers: {
        "content-type": "application/json",
        "cache-control": "public, s-maxage=10, stale-while-revalidate=30",
      },
    })
  } catch {
    return NextResponse.json({ live_count: 0, live: [], next: null }, { status: 200 })
  }
}
