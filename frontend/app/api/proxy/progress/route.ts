import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Cheap proxy for the group-stage progress strip in the TopBar.
export async function GET() {
  try {
    const res = await fetch(`${BACKEND}/tournament/progress`, { cache: "no-store" })
    const data = await res.json()
    return NextResponse.json(data, { status: res.status })
  } catch (e) {
    return NextResponse.json({ error: String(e) }, { status: 502 })
  }
}
