import type { MetadataRoute } from "next"

// Note: the edge (Cloudflare) may serve its own managed robots.txt in front of this.
// We still declare it so self-hosted runs and the sitemap reference are correct.
//
// /admin and /api/admin are gated by an HttpOnly cookie + backend bearer, but
// crawlers should never have heard of them in the first place — adding the
// disallow is belt-and-braces.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: ["/admin", "/admin/", "/api/admin"],
    },
    sitemap: "https://wc26.tinjak.com/sitemap.xml",
    host: "https://wc26.tinjak.com",
  }
}
