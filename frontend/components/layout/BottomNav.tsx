"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { useState, useEffect } from "react"
import {
  Clock, TrendingUp, Layers, GitFork, MoreHorizontal,
  Trophy, Table2, Sparkles, Gauge, Zap, Info, X,
  Bot, ClipboardList, UserCheck,
} from "lucide-react"

const PRIMARY = [
  { href: "/", label: "Matches", icon: Clock },
  { href: "/live", label: "Live", icon: Zap },
  { href: "/value", label: "Value", icon: TrendingUp },
  { href: "/acca", label: "Acca", icon: Layers },
  { href: "/bracket", label: "Bracket", icon: GitFork },
]

type SheetItem = { href: string; label: string; icon: typeof Trophy; hint: string }

const SHEET_GROUPS: { title: string; items: SheetItem[] }[] = [
  {
    title: "Tournament",
    items: [
      { href: "/winner", label: "World Cup Odds", icon: Trophy, hint: "Outright winner probabilities" },
      { href: "/groups", label: "Group Tables", icon: Table2, hint: "Live standings, all 12 groups" },
      { href: "/scenarios", label: "Scenarios", icon: Sparkles, hint: "What each team needs in MD3" },
      { href: "/match3", label: "Match 3 Watch", icon: Zap, hint: "Rotation risk in last group game" },
    ],
  },
  {
    title: "Picks & Tracking",
    items: [
      { href: "/model-picks", label: "Model Picks", icon: Bot, hint: "Daily auto-curated edge bets" },
      { href: "/predictions", label: "Track Record", icon: ClipboardList, hint: "Every logged pick, settled" },
      { href: "/my-picks", label: "My Picks", icon: UserCheck, hint: "Your own calls vs the model" },
      { href: "/performance", label: "Report Card", icon: Gauge, hint: "Model accuracy + calibration" },
    ],
  },
  {
    title: "About",
    items: [
      { href: "/how-it-works", label: "How It Works", icon: Info, hint: "Model methodology" },
    ],
  },
]

// Pages that live in the sheet — when one of them is active, light up the "More" button
const SHEET_PATHS = new Set(SHEET_GROUPS.flatMap((g) => g.items.map((i) => i.href)))

export function BottomNav() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)

  // Close sheet on route change
  useEffect(() => {
    setOpen(false)
  }, [pathname])

  // Lock scroll + escape to close
  useEffect(() => {
    if (!open) return
    document.body.style.overflow = "hidden"
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false)
    }
    window.addEventListener("keydown", onKey)
    return () => {
      document.body.style.overflow = ""
      window.removeEventListener("keydown", onKey)
    }
  }, [open])

  const moreActive = SHEET_PATHS.has(pathname) || open

  return (
    <>
      {/* Sheet backdrop */}
      {open && (
        <div
          className="lg:hidden fixed inset-0 z-30 bg-black/60 backdrop-blur-sm animate-in fade-in"
          onClick={() => setOpen(false)}
          aria-hidden="true"
        />
      )}

      {/* Slide-up sheet. Flex column so the scroll area flex-fills and the
          whole list is reachable. Bottom padding clears the fixed nav bar +
          the iOS home indicator, so the last menu item never hides behind the
          tab bar (the bug: a fixed inner max-height let the list run under the
          nav and the final rows couldn't be scrolled into view). */}
      <div
        className={`lg:hidden fixed left-0 right-0 z-40 bg-surface-1 border-t border-edge rounded-t-2xl shadow-2xl transition-transform duration-300 ease-out flex flex-col ${
          open ? "translate-y-0" : "translate-y-full"
        }`}
        style={{
          bottom: 0,
          maxHeight: "85dvh",
        }}
        role="dialog"
        aria-modal="true"
        aria-label="More navigation"
      >
        {/* Grab handle */}
        <div className="flex justify-center pt-2.5 pb-1 shrink-0">
          <div className="w-10 h-1 rounded-full bg-slate-700" />
        </div>

        <div className="flex items-center justify-between px-5 pb-3 border-b border-edge shrink-0">
          <p className="text-[14px] font-bold text-white">More</p>
          <button
            onClick={() => setOpen(false)}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-surface-2"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div
          className="overflow-y-auto overscroll-contain px-2 py-2 flex-1 min-h-0"
          style={{
            // Clear the fixed bottom nav (3.75rem) + the iOS home indicator so
            // the final item is always scrollable into view above the tab bar.
            paddingBottom: "calc(3.75rem + env(safe-area-inset-bottom) + 1rem)",
          }}
        >
          {SHEET_GROUPS.map((group) => (
            <div key={group.title} className="mb-2">
              <p className="px-3 pt-2 pb-1 text-[10px] font-bold tracking-widest text-slate-600 uppercase">
                {group.title}
              </p>
              {group.items.map(({ href, label, icon: Icon, hint }) => {
                const active = pathname === href
                return (
                  <Link
                    key={href}
                    href={href}
                    className={`flex items-center gap-3 px-3 py-3 rounded-xl transition-colors ${
                      active ? "bg-emerald-500/10" : "hover:bg-surface-2 active:bg-surface-2"
                    }`}
                  >
                    <span
                      className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 ${
                        active ? "bg-emerald-500/20 text-emerald-300" : "bg-surface-2 text-slate-400"
                      }`}
                    >
                      <Icon size={17} strokeWidth={active ? 2.5 : 1.8} />
                    </span>
                    <span className="flex-1 min-w-0">
                      <span className={`block text-[13px] font-bold ${active ? "text-emerald-300" : "text-slate-100"}`}>
                        {label}
                      </span>
                      <span className="block text-[11px] text-slate-500 truncate">{hint}</span>
                    </span>
                  </Link>
                )
              })}
            </div>
          ))}
        </div>
      </div>

      {/* Fixed bottom nav: 4 primary + More. iOS-style frosted glass + tap-scale
          feedback so it feels native. backdrop-blur needs the surface alpha
          dropped a touch; bg-surface-1/85 keeps theme tokens in charge. */}
      <nav
        className="lg:hidden fixed bottom-0 left-0 right-0 z-20 bg-surface-1/85 backdrop-blur-md border-t border-edge flex items-stretch"
        style={{
          height: "calc(3.75rem + env(safe-area-inset-bottom))",
          paddingBottom: "env(safe-area-inset-bottom)",
        }}
      >
        {PRIMARY.map(({ href, label, icon: Icon }) => {
          const active = pathname === href
          return (
            <Link
              key={href}
              href={href}
              className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-all duration-150 relative active:scale-[0.94] ${
                active ? "text-emerald-400" : "text-slate-600 hover:text-slate-400"
              }`}
            >
              {active && (
                <span className="absolute top-0 left-1/2 -translate-x-1/2 w-7 h-[2px] bg-emerald-400 rounded-full shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
              )}
              <Icon size={19} strokeWidth={active ? 2.5 : 1.8} />
              <span>{label}</span>
            </Link>
          )
        })}
        <button
          onClick={() => setOpen((v) => !v)}
          className={`flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-all duration-150 relative active:scale-[0.94] ${
            moreActive ? "text-emerald-400" : "text-slate-600 hover:text-slate-400"
          }`}
          aria-label="More navigation"
          aria-expanded={open}
        >
          {moreActive && (
            <span className="absolute top-0 left-1/2 -translate-x-1/2 w-7 h-[2px] bg-emerald-400 rounded-full shadow-[0_0_8px_rgba(52,211,153,0.5)]" />
          )}
          <MoreHorizontal size={19} strokeWidth={moreActive ? 2.5 : 1.8} />
          <span>More</span>
        </button>
      </nav>
    </>
  )
}
