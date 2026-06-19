import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Forward bet-builder best-price lookups to the backend. Same pattern as the
// analyze-multi proxy.
export async function POST(req: Request) {
  try {
    const body = await req.text()
    const res = await fetch(`${BACKEND}/betting/multi/best-prices`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      cache: "no-store",
    })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e) {
    return NextResponse.json(
      { error: `Proxy failed: ${(e as Error).message}` },
      { status: 502 },
    )
  }
}
