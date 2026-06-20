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
  // The negative-lookahead constraint `(?!admin/)` keeps the wholesale rule
  // from matching any /api/admin/* path, so those fall through to the
  // file-system handlers we define under app/api/admin/. A bare no-op
  // beforeFiles rewrite does NOT work here — Next.js drops same-source-as-
  // destination rewrites entirely.
  async rewrites() {
    return [
      {
        source: "/api/:path((?!admin/).*)",
        destination: `${process.env.BACKEND_URL ?? "http://wc26-backend:8000"}/:path*`,
      },
    ]
  },
}

export default config
