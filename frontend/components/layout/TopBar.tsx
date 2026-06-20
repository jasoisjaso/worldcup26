import Link from "next/link"
import { ChevronLeft } from "lucide-react"
import { TimezoneSelect } from "./TimezoneSelect"
import { SearchBar } from "./SearchBar"
import { SearchPill } from "./SearchPill"
import { GroupStageProgress } from "@/components/common/GroupStageProgress"
import { LiveTickerBar } from "@/components/live/LiveTickerBar"

interface TopBarProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
  backHref?: string
  backLabel?: string
}

function BallMark() {
  return (
    <svg width="22" height="22" viewBox="0 0 22 22" fill="none" aria-hidden="true" className="flex-shrink-0">
      <circle cx="11" cy="11" r="10" stroke="#10b981" strokeWidth="1.2"/>
      <path d="M11 3L14.2 6.5L13 10.5H9L7.8 6.5Z" fill="#10b981"/>
      <path d="M14.2 6.5L18.5 8.5M13 10.5L16 14M9 10.5L6 14M7.8 6.5L3.5 8.5"
            stroke="#10b981" strokeWidth="0.8" strokeLinecap="round" opacity="0.45"/>
    </svg>
  )
}

export function TopBar({ title, subtitle, action, backHref, backLabel }: TopBarProps) {
  return (
    // iOS PWA: viewport-fit=cover + black-translucent status bar means the Dynamic
    // Island and notch sit ON TOP of position:sticky content unless we eat the
    // env(safe-area-inset-top) ourselves. paddingTop on the outer container does
    // the right thing without changing layout on desktop (env() resolves to 0px).
    <div
      className="sticky top-0 z-30 border-b glass shadow-[0_8px_24px_-18px_rgba(0,0,0,0.85)]"
      style={{ paddingTop: "env(safe-area-inset-top)" }}
    >
      {/* Live ticker mounted INSIDE the safe-area-padded sticky shell so the
          iPhone Dynamic Island doesn't cover it, and so it scrolls in lock-step
          with the rest of the chrome. Hides itself when nothing's in play. */}
      <LiveTickerBar />

      <div className="flex items-center justify-between px-3 sm:px-4 py-3">
        <div className="flex items-center gap-2 min-w-0">
          {backHref ? (
            <Link
              href={backHref}
              className="-ml-1 mr-1 flex items-center gap-0.5 pl-1 pr-1.5 py-1.5 rounded-lg text-slate-500 hover:text-emerald-300 hover:bg-surface-2 active:bg-surface-2 transition-colors shrink-0"
              aria-label={backLabel ? `Back to ${backLabel}` : "Back"}
            >
              <ChevronLeft size={20} strokeWidth={2.2} />
              {backLabel && (
                <span className="hidden sm:inline text-[11px] font-semibold max-w-[120px] truncate">{backLabel}</span>
              )}
            </Link>
          ) : (
            <BallMark />
          )}
          <div className="min-w-0">
            <h1 className="font-display text-[15px] font-semibold text-ink tracking-tight truncate leading-tight">{title}</h1>
            {subtitle && <p className="text-[11px] text-slate-500 mt-0 leading-tight truncate">{subtitle}</p>}
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          {action}
          <SearchBar />
          <TimezoneSelect />
        </div>
      </div>
      {/* Mobile-only search pill — full-width tap target so search is
          impossible to miss on phones. Desktop uses the magnifier in the
          action slot above instead. */}
      <div className="px-3 pb-2 sm:hidden">
        <SearchPill />
      </div>
      {/* Group-stage progress strip — sitewide, gives tournament momentum at a glance. */}
      <div className="px-3 sm:px-4 pb-2">
        <GroupStageProgress />
      </div>
    </div>
  )
}
