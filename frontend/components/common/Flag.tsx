interface FlagProps {
  code: string
  name: string
  size?: "sm" | "md" | "lg"
}

const SIZES = {
  sm: { w: 20, h: 14, cls: "rounded-sm" },
  md: { w: 32, h: 22, cls: "rounded" },
  lg: { w: 42, h: 30, cls: "rounded-md" },
}

export function Flag({ code, name, size = "md" }: FlagProps) {
  const { w, h, cls } = SIZES[size]
  return (
    <img
      src={`https://flagcdn.com/w${w * 2}/${code}.png`}
      alt={`${name} flag`}
      width={w}
      height={h}
      className={`${cls} border border-white/5 object-cover bg-slate-800 flex-shrink-0`}
    />
  )
}
