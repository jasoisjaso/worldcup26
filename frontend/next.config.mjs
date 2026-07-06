/** @type {import('next').NextConfig} */
const config = {
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "flagcdn.com" },
    ],
  },
  // Browser-side fetches need a same-origin path so they don't try to hit the
  // user's own machine. The Next server proxies /api/* to the backend
  // container (BACKEND_URL is reachable from the Next runtime, not from the
  // browser). Server-side fetches in lib/api.ts skip this and go direct.
  //
  // The wholesale /api/* → backend rewrite below is `afterFiles`, which in
  // Next.js overrides file-system route handlers (only exact static matches
  // beat it; dynamic catch-alls lose). That silently shadowed the admin
  // proxy under app/api/admin/proxy/[...path] and made every request
  // 404 with FastAPI's detail shape.
  //
  // The negative-lookahead constraint keeps the wholesale rule from matching
  // any path that has its OWN file-system route handler, so those fall through
  // to the handlers we define under app/api/*. Without this, the afterFiles
  // rewrite shadows dynamic route handlers (e.g. app/api/proxy/teams/[code])
  // and the request hits the backend as /proxy/teams/br -> FastAPI 404. Static
  // routes (model-multis) happened to win the match; dynamic ones lost. Every
  // namespace with a dedicated route handler must be listed here.
  // A bare no-op beforeFiles rewrite does NOT work — Next.js drops same-source-
  // as-destination rewrites entirely.
  //
  // NOTE 2026-06-24: 'push/' was previously in this exclusion but no Next.js
  // route handler for /api/push exists — that made every /api/push/* request
  // return the SPA 404 page silently (PushSubscribe.tsx's try/catch swallowed
  // the failure so value-pick notifications never actually subscribed). The
  // exclusion was stale defensive plumbing; removed so /api/push/* proxies
  // to FastAPI like every other backend route.
  async rewrites() {
    return [
      {
        source: "/api/:path((?!admin/|proxy/|wcdata/).*)",
        destination: `${process.env.BACKEND_URL ?? "http://wc26-backend:8000"}/:path*`,
      },
    ]
  },
  // The service worker MUST NOT be HTTP-cached — a stale sw.js means a broken
  // worker (e.g. the v4 null-response bug) keeps running for up to the cache
  // TTL before the browser even checks for an update. no-store forces a fresh
  // fetch every time so a version bump takes effect on the next navigation.
  async headers() {
    return [
      {
        source: "/sw.js",
        headers: [
          { key: "Cache-Control", value: "no-cache, no-store, must-revalidate" },
        ],
      },
    ]
  },
}

export default config
