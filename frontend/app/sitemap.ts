import type { MetadataRoute } from "next"
import { api } from "@/lib/api"

const SITE = "https://wc26.tinjak.com"

// Re-enumerated hourly so newly-resolved knockout fixtures appear without a deploy.
export const revalidate = 3600

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticPaths = ["", "/winner", "/value", "/groups", "/acca", "/performance", "/predictions", "/how-it-works"]
  const staticEntries: MetadataRoute.Sitemap = staticPaths.map((p) => ({
    url: `${SITE}${p}`,
    changeFrequency: "daily",
    priority: p === "" ? 1 : 0.8,
  }))

  // The 104 match pages and every team page already exist behind the API; list them so
  // "X vs Y prediction" pages are crawlable instead of hidden behind opaque numeric IDs.
  let dynamicEntries: MetadataRoute.Sitemap = []
  try {
    const matches = await api.matches()
    const matchEntries: MetadataRoute.Sitemap = matches.map((m) => ({
      url: `${SITE}/match/${m.id}`,
      changeFrequency: "hourly",
      priority: 0.9,
    }))
    const codes = new Set<string>()
    for (const m of matches) {
      if (m.home?.code) codes.add(m.home.code)
      if (m.away?.code) codes.add(m.away.code)
    }
    const teamEntries: MetadataRoute.Sitemap = Array.from(codes).map((code) => ({
      url: `${SITE}/team/${code}`,
      changeFrequency: "daily",
      priority: 0.6,
    }))
    dynamicEntries = [...matchEntries, ...teamEntries]
  } catch {
    // If the API is briefly unreachable at build/revalidate, still serve the static map.
  }

  return [...staticEntries, ...dynamicEntries]
}
