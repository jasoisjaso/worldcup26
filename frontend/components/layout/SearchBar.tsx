"use client"

import { useEffect, useState, useCallback } from "react"
import dynamic from "next/dynamic"
import { Search } from "lucide-react"

const SearchPanel = dynamic(() => import("./SearchPanel").then((m) => m.SearchPanel), { ssr: false })

/**
 * Desktop / tablet search trigger — compact magnifier icon that lives in the
 * TopBar action area. Hidden below the `sm` breakpoint so it doesn't crowd the
 * right-hand slot on phones; mobile users get the SearchPill under the title.
 */
export function SearchBar() {
  const [open, setOpen] = useState(false)
  const close = useCallback(() => setOpen(false), [])

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
        className="hidden sm:inline-flex items-center justify-center p-1.5 rounded-lg text-slate-500 hover:text-emerald-300 hover:bg-surface-2 transition-colors"
        aria-label="Search teams and players"
        title="Search (Ctrl+K)"
      >
        <Search size={18} strokeWidth={2} />
      </button>
      {open && <SearchPanel onClose={close} />}
    </>
  )
}
