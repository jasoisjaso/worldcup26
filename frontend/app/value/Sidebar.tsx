"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Clock, TrendingUp, Layers, BarChart2, Zap, Info, Table2 } from "lucide-react"

const NAV = [
  { href: "/", label: "Matches", icon: Clock, group: "Tournament" },
  { href: "/value", label: "Value Board", icon: TrendingUp, group: "Tournament" },
  { href: "/acca", label: "Acca Builder", icon: Layers, group: "Tournament" },
  { href: "/groups", label: "Group Tables", icon: Table2, group: "Tournament" },
  { href: "/predictions", label: "My Predictions", icon: BarChart2, group: "Tracking" },
  { href: "/match3", label: "Match 3 Watch", icon: Zap, group: "Tracking" },
  { href: "/how-it-works", label: "How It Works", icon: Info, group: "Info" },
]

const GROUPS = ["Tournament", "Tracking", "Info"]

export function Sidebar() {
  const pathname = usePathname()

  return (
    <aside className="hidden lg:flex w-[220px] bg-surface-2 border-r border-edge flex-col flex-shrink-0">
      <div className="px-5 py-5 border-b border-edge">
        <span className="text-[17px] font-extrabold tracking-tight">
          WC<span className="text-blue-500">2026</span>
        </span>
        <p className="text-[10px] text-slate-500 mt-0.5 font-medium">Predictor</p>
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
                    ? "bg-surface-2 text-white border-blue-500"
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
