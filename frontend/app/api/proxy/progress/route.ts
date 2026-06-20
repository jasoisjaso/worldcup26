import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Cheap proxy for the group-stage progress strip in the TopBar.
// Cached 30s at the edge with a 60s SWR so multiple tabs / refreshes don't
// each round-trip the FastAPI backend — the underlying data only ticks when a
// match finishes.
export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/tournament/progress`, {
      next: { revalidate: 30 },
    })
    const data = await res.json()
    return NextResponse.json(data, {
      status: res.status,
      headers: { "cache-control": "public, s-maxage=30, stale-while-revalidate=60" },
    })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 })
  }
}
