import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://wc26-backend:8000"

export async function GET(
  req: Request,
  { params }: { params: { path: string[] } }
) {
  const subpath = (params.path || []).join("/")
  const url = new URL(req.url)
  const target = `${BACKEND}/wcdata/${subpath}${url.search}`
  try {
    const res = await fetch(target, { cache: "no-store" })
    const text = await res.text()
    return new NextResponse(text, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    })
  } catch (err: any) {
    return NextResponse.json({ error: "wcdata proxy failed", target, msg: err?.message }, { status: 502 })
  }
}
