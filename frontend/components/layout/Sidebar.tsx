"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Clock, TrendingUp, Layers, BarChart2, Zap, Info, Table2, Trophy, Gauge, GitFork, Target } from "lucide-react"

const NAV = [
  { href: "/", label: "Matches", icon: Clock, group: "Tournament" },
  { href: "/winner", label: "World Cup Odds", icon: Trophy, group: "Tournament" },
  { href: "/bracket", label: "Knockout Bracket", icon: GitFork, group: "Tournament" },
  { href: "/scenarios", label: "MD3 Scenarios", icon: Target, group: "Tournament" },
  { href: "/value", label: "Value Board", icon: TrendingUp, group: "Tournament" },
  { href: "/acca", label: "Acca Builder", icon: Layers, group: "Tournament" },
  { href: "/groups", label: "Group Tables", icon: Table2, group: "Tournament" },
  { href: "/performance", label: "Report Card", icon: Gauge, group: "Tracking" },
  { href: "/predictions", label: "My Predictions", icon: BarChart2, group: "Tracking" },
  { href: "/match3", label: "Match 3 Watch", icon: Zap, group: "Tracking" },
  { href: "/how-it-works", label: "How It Works", icon: Info, group: "Info" },
]

const GROUPS = ["Tournament", "Tracking", "Info"]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="hidden lg:flex w-[220px] bg-surface-1 border-r border-edge flex-col flex-shrink-0">
      <div className="px-5 py-4 border-b border-edge flex items-center gap-3">
        <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
          <circle cx="17" cy="17" r="16" fill="#040a0a"/>
          <circle cx="17" cy="17" r="16" fill="none" stroke="#10b981" strokeWidth="1.5"/>
          <path d="M17 4.5L21 10.5L19 16.5L15 16.5L13 10.5Z" fill="#10b981"/>
          <path d="M21 10.5L27 12L27.5 18.5L22.5 21.5L19 16.5Z" fill="#071a12" stroke="#0d3326" strokeWidth="0.7"/>
          <path d="M22.5 21.5L25.5 27.5L19.5 30L14.5 28L15 21.5Z" fill="#071a12" stroke="#0d3326" strokeWidth="0.7"/>
          <path d="M7 21.5L8 28L13 30L14.5 28L14.5 21.5Z" fill="#071a12" stroke="#0d3326" strokeWidth="0.7"/>
          <path d="M6.5 18.5L7 12L13 10.5L15 16.5L11.5 21.5Z" fill="#071a12" stroke="#0d3326" strokeWidth="0.7"/>
          <path d="M15 16.5L19 16.5L22.5 21.5L17 22.5L11.5 21.5Z" fill="#0a201a" stroke="#0d3326" strokeWidth="0.7"/>
        </svg>
        <div>
          <p className="text-[18px] font-black tracking-tighter text-white leading-none">
            WC<span className="text-emerald-400">26</span>
          </p>
          <p className="text-[9px] font-bold tracking-widest text-slate-500 uppercase mt-0.5">
            Predictor
          </p>
        </div>
      </div>

      {GROUPS.map((group) => (
        <div key={group} className="pt-4 pb-1">
          <p className="px-4 pb-1.5 text-[10px] font-bold text-slate-600 uppercase tracking-widest">
            {group}
          </p>
          {NAV.filter((n) => n.group === group).map(({ href, label, icon: Icon }) => {
            const active = pathname === href
            return (
              <Link
                key={href}
                href={href}
                className={[
                  "flex items-center gap-2.5 px-4 py-2.5 text-[13px] font-medium transition-colors",
                  "border-l-2",
                  active
                    ? "bg-emerald-500/10 text-emerald-300 border-emerald-500"
                    : "text-slate-500 border-transparent hover:text-slate-300 hover:bg-surface-2",
                ].join(" ")}
              >
                <Icon size={15} />
                {label}
              </Link>
            )
          })}
        </div>
      ))}
    </aside>
  )
}
