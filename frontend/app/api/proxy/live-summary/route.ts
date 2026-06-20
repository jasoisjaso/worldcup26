import { NextResponse } from "next/server"

// Same-origin proxy for the LiveTicker client poller. Backend lives on a
// docker-internal hostname not reachable from the browser; this route forwards.
export const dynamic = "force-dynamic"

export async function GET() {
  const base = process.env.BACKEND_URL ?? "http://wc26-backend:8000"
  try {
    const r = await fetch(`${base}/live/summary`, { cache: "no-store" })
    const body = await r.text()
    return new NextResponse(body, {
      status: r.status,
      headers: { "content-type": "application/json" },
    })
  } catch {
    return NextResponse.json({ live_count: 0, live: [], next: null }, { status: 200 })
  }
}
