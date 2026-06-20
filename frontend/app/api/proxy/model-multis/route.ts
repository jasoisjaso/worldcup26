import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Proxy for the model-multis listing. Frontend reads it for SSR + client refresh.
// 60s s-maxage matches the scheduler tick — picks only get added when the
// daily/settle job fires, so a sub-minute refresh window adds zero freshness.
export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/picks/model-multis`, {
      next: { revalidate: 60 },
    })
    const data = await res.json()
    return NextResponse.json(data, {
      status: res.status,
      headers: { "cache-control": "public, s-maxage=60, stale-while-revalidate=120" },
    })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 })
  }
}
