import type { MetadataRoute } from "next"

// Note: the edge (Cloudflare) may serve its own managed robots.txt in front of this.
// We still declare it so self-hosted runs and the sitemap reference are correct.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", allow: "/" },
    sitemap: "https://wc26.tinjak.com/sitemap.xml",
    host: "https://wc26.tinjak.com",
  }
}
