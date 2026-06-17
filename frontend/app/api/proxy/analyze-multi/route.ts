import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Browser -> Next server -> backend. NEXT_PUBLIC_API_URL points at the docker-internal
// hostname, so the browser can't reach the backend directly; the custom-multi analyzer
// is a client component, so it posts here and we forward.
export async function POST(req: Request) {
  try {
    const body = await req.text()
    const res = await fetch(`${BACKEND}/betting/analyze-multi`, {
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
