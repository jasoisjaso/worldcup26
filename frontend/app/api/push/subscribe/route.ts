import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

export async function POST(request: Request) {
  try {
    const body = await request.json()
    const res = await fetch(`${BACKEND}/push/subscribe`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ status: "error" }, { status: 502 })
  }
}
