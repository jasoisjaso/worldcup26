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
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.BACKEND_URL ?? "http://wc26-backend:8000"}/:path*`,
      },
    ]
  },
}

export default config
