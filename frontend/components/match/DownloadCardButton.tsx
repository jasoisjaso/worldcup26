"use client"

import { Download } from "lucide-react"

/**
 * Vertical 9:16 PNG download button. Hits /match/[id]/share which is a Next
 * `next/og` route returning a 1080×1920 image suitable for TikTok / IG Reels /
 * YT Shorts. The `download` attribute on the link triggers a save instead of
 * a navigation — works in every modern browser including mobile Safari.
 */
export function DownloadCardButton({
  matchId,
  homeName,
  awayName,
  className = "",
}: {
  matchId: string
  homeName: string
  awayName: string
  className?: string
}) {
  const filename = `${homeName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-vs-${awayName.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-wc26.png`
  return (
    <a
      href={`/match/${matchId}/share`}
      download={filename}
      target="_blank"
      rel="noopener noreferrer"
      className={[
        "flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg border transition-colors",
        "bg-emerald-950/40 border-emerald-800/50 text-emerald-300 hover:bg-emerald-900/40 hover:border-emerald-700",
        className,
      ].join(" ")}
      title="Download a 1080×1920 PNG for TikTok / Instagram"
    >
      <Download size={13} />
      Share card
    </a>
  )
}
