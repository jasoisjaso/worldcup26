import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Proxy for the model-multis listing. Frontend reads it for SSR + client refresh.
export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/picks/model-multis`, { cache: "no-store" })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 })
  }
}
