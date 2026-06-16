"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Clock, TrendingUp, BarChart2, Table2, Trophy, Gauge } from "lucide-react"

const NAV = [
  { href: "/", label: "Matches", icon: Clock },
  { href: "/winner", label: "Odds", icon: Trophy },
  { href: "/value", label: "Value", icon: TrendingUp },
  { href: "/performance", label: "Report", icon: Gauge },
  { href: "/predictions", label: "Picks", icon: BarChart2 },
  { href: "/groups", label: "Tables", icon: Table2 },
]

export function BottomNav() {
  const pathname = usePathname()

  return (
    <nav
      className="lg:hidden fixed bottom-0 left-0 right-0 z-20 bg-surface-1 border-t border-edge flex items-stretch"
      style={{ height: "calc(3.5rem + env(safe-area-inset-bottom))", paddingBottom: "env(safe-area-inset-bottom)" }}
    >
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors relative",
              active ? "text-amber-400" : "text-slate-600 hover:text-slate-400",
            ].join(" ")}
          >
            {active && (
              <span className="absolute top-0 left-1/2 -translate-x-1/2 w-6 h-[2px] bg-amber-400 rounded-full" />
            )}
            <Icon size={18} strokeWidth={active ? 2.5 : 1.8} />
            <span>{label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
