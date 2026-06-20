import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

/**
 * Validate the supplied admin token against the backend, then mint an
 * HttpOnly cookie if it works. The token itself never reaches the client
 * after this exchange — the cookie is the only thing the browser sees, and it
 * is read server-side by the /admin pages and the /api/admin/proxy bridge.
 *
 * We probe a cheap admin endpoint (/harvester/status) with the token to
 * confirm; this avoids leaking validity-vs-availability when WC26_ADMIN_TOKEN
 * is unset on the server (the backend will 503 either way).
 */
export async function POST(req: Request) {
  let token = ""
  try {
    const body = await req.json()
    token = (body?.token ?? "").toString().trim()
  } catch {
    return NextResponse.json({ ok: false, error: "Bad payload" }, { status: 400 })
  }
  if (!token) {
    return NextResponse.json({ ok: false, error: "Token required" }, { status: 400 })
  }

  let probe: Response
  try {
    probe = await fetch(`${BACKEND}/harvester/status`, {
      headers: { "X-Admin-Token": token },
      cache: "no-store",
    })
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `Backend unreachable: ${(e as Error).message}` },
      { status: 502 },
    )
  }

  if (probe.status === 503) {
    return NextResponse.json(
      { ok: false, error: "Admin token not configured on the backend (set WC26_ADMIN_TOKEN)." },
      { status: 503 },
    )
  }
  if (probe.status === 401) {
    return NextResponse.json({ ok: false, error: "Invalid token." }, { status: 401 })
  }
  if (!probe.ok) {
    return NextResponse.json(
      { ok: false, error: `Backend returned ${probe.status}.` },
      { status: 502 },
    )
  }

  const res = NextResponse.json({ ok: true })
  // 12h session. The token itself is the only credential; rotating
  // WC26_ADMIN_TOKEN invalidates every minted cookie immediately because the
  // proxy bridge re-presents it on every admin call.
  res.cookies.set("wc26_admin", token, {
    httpOnly: true,
    secure: true,
    sameSite: "lax",
    path: "/",
    maxAge: 60 * 60 * 12,
  })
  return res
}


export async function DELETE() {
  const res = NextResponse.json({ ok: true })
  res.cookies.set("wc26_admin", "", { path: "/", maxAge: 0 })
  return res
}
