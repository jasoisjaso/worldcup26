import { NextResponse } from "next/server"
import { cookies } from "next/headers"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

/**
 * Server-side bridge for admin calls. The browser hits
 *   /api/admin/proxy/harvester/overview
 * we re-emit
 *   GET http://wc26-backend:8000/harvester/overview
 * with the admin cookie injected as a bearer header. The token never leaves
 * the server.
 *
 * Wildcards both GET and POST because the admin surface needs both
 * (run-one / seed / pause are POSTs).
 */
async function forward(req: Request, params: { path: string[] }, method: "GET" | "POST") {
  const cookieStore = cookies()
  const token = cookieStore.get("wc26_admin")?.value
  if (!token) {
    return NextResponse.json({ error: "Not authenticated" }, { status: 401 })
  }

  const subpath = (params.path || []).join("/")
  const url = new URL(req.url)
  const target = `${BACKEND}/${subpath}${url.search}`

  const init: RequestInit = {
    method,
    headers: {
      "X-Admin-Token": token,
      ...(method === "POST" ? { "content-type": "application/json" } : {}),
    },
    cache: "no-store",
  }
  if (method === "POST") {
    try {
      init.body = await req.text()
    } catch {
      init.body = ""
    }
  }

  try {
    const res = await fetch(target, init)
    const body = await res.text()
    return new NextResponse(body, {
      status: res.status,
      headers: { "content-type": res.headers.get("content-type") ?? "application/json" },
    })
  } catch (e) {
    return NextResponse.json(
      { error: `Admin proxy failed: ${(e as Error).message}`, target },
      { status: 502 },
    )
  }
}


export async function GET(req: Request, ctx: { params: { path: string[] } }) {
  return forward(req, ctx.params, "GET")
}


export async function POST(req: Request, ctx: { params: { path: string[] } }) {
  return forward(req, ctx.params, "POST")
}
