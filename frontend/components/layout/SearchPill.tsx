"use client"

import { useState, useCallback, useEffect } from "react"
import dynamic from "next/dynamic"
import { Search } from "lucide-react"

// Lazy-load the heavy panel — the pill itself is cheap, the overlay
// (event listeners, fetch hook, results list) only mounts when tapped.
const SearchPanel = dynamic(() => import("./SearchPanel").then((m) => m.SearchPanel), { ssr: false })

/**
 * Mobile-first search trigger. Renders a full-width pill under the page title
 * so it reads as "Search teams or players" without the user hunting for an
 * icon. On tap, mounts and opens the SearchPanel overlay. Hidden on tablet+
 * (`sm:hidden`) because the desktop magnifier in TopBar covers those breakpoints.
 */
export function SearchPill() {
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])

  // Keep Ctrl/Cmd+K working from anywhere on mobile too.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault()
        setOpen(true)
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="sm:hidden flex items-center gap-2 w-full px-3 py-2 rounded-xl bg-surface-2/70 border border-edge text-[12.5px] text-slate-400 hover:bg-surface-2 active:scale-[0.99] transition-all"
        aria-label="Open search"
      >
        <Search size={15} className="text-slate-500 shrink-0" />
        <span className="flex-1 text-left">Search teams or players</span>
        <span className="text-[10px] text-slate-600 tracking-widest">TAP</span>
      </button>
      {open && <SearchPanel onClose={close} />}
    </>
  )
}
