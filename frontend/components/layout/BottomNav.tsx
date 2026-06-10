"use client"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { Clock, TrendingUp, Layers, BarChart2, Zap, Table2 } from "lucide-react"

const NAV = [
  { href: "/", label: "Matches", icon: Clock },
  { href: "/value", label: "Value", icon: TrendingUp },
  { href: "/acca", label: "Acca", icon: Layers },
  { href: "/predictions", label: "Picks", icon: BarChart2 },
  { href: "/match3", label: "Match 3", icon: Zap },
  { href: "/groups", label: "Tables", icon: Table2 },
]

export function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="lg:hidden fixed bottom-0 left-0 right-0 z-20 bg-[#0f1320] border-t border-[#1a2033] flex items-stretch" style={{ height: "calc(3.5rem + env(safe-area-inset-bottom))", paddingBottom: "env(safe-area-inset-bottom)" }}>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = pathname === href
        return (
          <Link
            key={href}
            href={href}
            className={[
              "flex-1 flex flex-col items-center justify-center gap-0.5 text-[10px] font-semibold transition-colors",
              active ? "text-blue-400" : "text-slate-600 hover:text-slate-400",
            ].join(" ")}
          >
            <Icon size={18} strokeWidth={active ? 2.5 : 2} />
            <span>{label}</span>
          </Link>
        )
      })}
    </nav>
  )
}
