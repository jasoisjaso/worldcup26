interface TopBarProps {
  title: string
  subtitle?: string
  action?: React.ReactNode
}

export function TopBar({ title, subtitle, action }: TopBarProps) {
  return (
    <div className="flex items-center justify-between px-3 sm:px-6 py-3 sm:py-4 border-b border-[#1a2033] bg-[#0a0d14] sticky top-0 z-10">
      <div>
        <h1 className="text-[15px] sm:text-[17px] font-bold">{title}</h1>
        {subtitle && <p className="text-[12px] text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {action}
    </div>
  )
}
