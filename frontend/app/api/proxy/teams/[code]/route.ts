import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

export async function GET(
  _req: Request,
  { params }: { params: { code: string } }
) {
  try {
    const res = await fetch(`${BACKEND}/teams/${params.code}/profile`, {
      next: { revalidate: 300 },
    })
    const data = await res.json()
    return NextResponse.json(data)
  } catch {
    return NextResponse.json({ error: "Failed to fetch team profile" }, { status: 500 })
  }
}
