/** @type {import('next').NextConfig} */
const config = {
  output: "standalone",
  images: {
    remotePatterns: [
      { protocol: "https", hostname: "flagcdn.com" },
    ],
  },
}

export default config
