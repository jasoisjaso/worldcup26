"use client"

import { useState, type ReactNode } from "react"
import { LayoutList, Users } from "lucide-react"

type View = "severity" | "team"

export function InjuryViews({
  bySeverity,
  byTeam,
}: {
  bySeverity: ReactNode
  byTeam: ReactNode
}) {
  const [view, setView] = useState<View>("severity")

  return (
    <>
      <div className="flex gap-1 mb-4 rounded-full border border-edge bg-surface-2 p-1 w-fit">
        <TabButton
          active={view === "severity"}
          onClick={() => setView("severity")}
          icon={<LayoutList className="w-3.5 h-3.5" />}
          label="By severity"
        />
        <TabButton
          active={view === "team"}
          onClick={() => setView("team")}
          icon={<Users className="w-3.5 h-3.5" />}
          label="By team"
        />
      </div>

      {view === "severity" ? bySeverity : byTeam}
    </>
  )
}

function TabButton({
  active,
  onClick,
  icon,
  label,
}: {
  active: boolean
  onClick: () => void
  icon: ReactNode
  label: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={[
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[11.5px] font-semibold transition-colors",
        active
          ? "bg-emerald-900/40 text-emerald-200"
          : "text-slate-500 hover:text-slate-300 hover:bg-white/[0.03]",
      ].join(" ")}
    >
      {icon}
      {label}
    </button>
  )
}
