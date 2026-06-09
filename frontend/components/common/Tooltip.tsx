"use client"
import { useState } from "react"
import { Info } from "lucide-react"

interface TooltipProps {
  content: string
}

export function Tooltip({ content }: TooltipProps) {
  const [open, setOpen] = useState(false)
  return (
    <span className="relative inline-flex items-center">
      <button
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="text-slate-600 hover:text-slate-400 transition-colors"
        aria-label="More information"
      >
        <Info size={12} />
      </button>
      {open && (
        <span className="absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-56 bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-[11px] text-slate-300 leading-relaxed z-50 shadow-xl">
          {content}
        </span>
      )}
    </span>
  )
}
