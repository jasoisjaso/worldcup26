"use client"
import { useId, useState } from "react"
import { Info } from "lucide-react"

interface TooltipProps {
  content: string
}

// Reachable by mouse (hover), touch (tap toggles) and keyboard (focus opens). The
// definition is always in the DOM and linked via aria-describedby, so screen-reader and
// touch users get the jargon explanation that hover-only tooltips hid from them.
export function Tooltip({ content }: TooltipProps) {
  const [open, setOpen] = useState(false)
  const id = useId()
  return (
    <span className="group relative inline-flex items-center">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        aria-describedby={id}
        aria-expanded={open}
        aria-label="What this means"
        className="text-slate-500 hover:text-emerald-400 focus-visible:text-emerald-400 focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50 rounded transition-colors"
      >
        <Info size={12} />
      </button>
      <span
        id={id}
        role="tooltip"
        className={`pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-56 -translate-x-1/2 rounded-lg border border-edge bg-surface-3 px-3 py-2 text-[11px] leading-relaxed text-slate-300 shadow-xl transition-opacity duration-150 group-hover:visible group-hover:opacity-100 ${
          open ? "visible opacity-100" : "invisible opacity-0"
        }`}
      >
        {content}
      </span>
    </span>
  )
}
