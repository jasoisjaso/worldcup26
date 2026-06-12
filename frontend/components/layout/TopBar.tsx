import { TimezoneSelect } from "./TimezoneSelect"

interface TopBarProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
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

export function TopBar({ title, subtitle, action }: TopBarProps) {
  return (
    <div className="flex items-center justify-between px-4 py-3 border-b border-[#131c2e] bg-[#060a0f]/95 backdrop-blur-sm sticky top-0 z-10">
      <div className="flex items-center gap-2.5 min-w-0">
        <BallMark />
        <div className="min-w-0">
          <h1 className="text-[15px] font-bold text-white tracking-tight truncate leading-tight">{title}</h1>
          {subtitle && <p className="text-[11px] text-slate-500 mt-0 leading-tight">{subtitle}</p>}
        </div>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {action}
        <TimezoneSelect />
      </div>
    </div>
  )
}
