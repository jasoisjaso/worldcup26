import { Zap } from "lucide-react"
import { formatEV } from "@/lib/utils"

interface EVBadgeProps {
  ev: number
  label?: string
}

export function EVBadge({ ev, label }: EVBadgeProps) {
  if (ev <= 0) return null
  return (
    <span className="inline-flex items-center gap-1 bg-green-950 border border-green-800 rounded-full px-2.5 py-0.5 text-[11px] font-bold text-green-400">
      <Zap size={11} />
      {label ? `${label} ${formatEV(ev)}` : formatEV(ev)}
    </span>
  )
}
