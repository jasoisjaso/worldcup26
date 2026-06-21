import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

// Group-table drawer + any other client-side team profile lookup goes through
// this proxy. The old version (1) swallowed backend errors into a 200 + JSON
// {error: ...} body which the drawer then misread, and (2) cached the response
// for 5 minutes — locking a transient failure in for the next viewer.
//
// New behaviour:
//   - Propagate the backend's HTTP status (404 stays a 404, 500 stays a 500).
//   - Short s-maxage so a cold backend can recover within ~30s; SWR keeps the
//     page snappy without hiding real outages.
//   - No bare 500 from this layer on its own exceptions either — surface the
//     real status code to the drawer so it can render a useful message.
export async function GET(
  _req: Request,
  { params }: { params: { code: string } }
) {
  try {
    const res = await fetch(`${BACKEND}/teams/${params.code}/profile`, {
      cache: "no-store",
    })
    const body = await res.text()
    return new NextResponse(body, {
      status: res.status,
      headers: {
        "content-type": res.headers.get("content-type") ?? "application/json",
        // 30s edge cache, 120s stale-while-revalidate. Keeps the drawer fast
        // on repeat opens without burning the backend on every group click.
        "cache-control": "public, s-maxage=30, stale-while-revalidate=120",
      },
    })
  } catch (err) {
    return NextResponse.json(
      { error: "team_profile_proxy_failed", detail: String(err) },
      { status: 502 },
    )
  }
}
