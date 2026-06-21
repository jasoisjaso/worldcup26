"use client"
import { useState } from "react"
import { Share2, Check, Copy } from "lucide-react"

interface ShareButtonProps {
  title: string
  text: string
  url?: string
  label?: string
  className?: string
  // Hide the text label below sm: useful in top bars (e.g. match page) where
  // the team-name title is the priority and the action row was crowded.
  compactOnMobile?: boolean
}

export function ShareButton({
  title,
  text,
  url = "https://wc26.tinjak.com",
  label = "Share",
  className = "",
  compactOnMobile = false,
}: ShareButtonProps) {
  const [copied, setCopied] = useState(false)

  async function handleShare() {
    const shareData = { title, text, url }
    try {
      if (typeof navigator !== "undefined" && navigator.share) {
        await navigator.share(shareData)
      } else {
        await navigator.clipboard.writeText(`${text}\n${url}`)
        setCopied(true)
        setTimeout(() => setCopied(false), 2000)
      }
    } catch {
      // user cancelled share or clipboard denied, fail silently
    }
  }

  return (
    <button
      onClick={handleShare}
      className={[
        "flex items-center gap-1.5 text-[12px] font-semibold px-3 py-1.5 rounded-lg border transition-colors",
        copied
          ? "bg-green-950 border-green-800/50 text-green-400"
          : "bg-surface-2 border-edge text-slate-400 hover:text-slate-200 hover:border-edge-strong",
        className,
      ].join(" ")}
    >
      {copied ? <Check size={13} /> : <Share2 size={13} />}
      <span className={compactOnMobile ? "hidden sm:inline" : ""}>
        {copied ? "Copied!" : label}
      </span>
    </button>
  )
}
