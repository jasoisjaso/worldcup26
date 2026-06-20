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
  // `afterFiles` rewrites override file-system routes, so the wholesale
  // /api/* → backend rule below would shadow any local /api/* handler we
  // write (it silently did for the admin proxy catch-all — requests fell
  // through to the backend and 404'd with FastAPI's detail shape). The
  // `beforeFiles` no-op rewrite for /api/admin/* short-circuits that:
  // Next.js sees the admin paths as already-routed and falls through to the
  // file-system handlers we defined under app/api/admin/.
  async rewrites() {
    return {
      beforeFiles: [
        { source: "/api/admin/:path*", destination: "/api/admin/:path*" },
      ],
      afterFiles: [
        {
          source: "/api/:path*",
          destination: `${process.env.BACKEND_URL ?? "http://wc26-backend:8000"}/:path*`,
        },
      ],
    }
  },
}

export default config
