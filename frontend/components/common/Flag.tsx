interface FlagProps {
  code?: string
  name: string
  size?: "sm" | "md" | "lg"
  url?: string
}

const SIZES = {
  sm: { w: 20, h: 14, cls: "rounded-sm", cdn: 40 },
  md: { w: 32, h: 22, cls: "rounded", cdn: 80 },
  lg: { w: 42, h: 30, cls: "rounded-md", cdn: 80 },
}

export function Flag({ code, name, size = "md", url }: FlagProps) {
  const { w, h, cls, cdn } = SIZES[size]
  let iso: string | undefined
  if (url) {
    iso = url.match(/\/([a-z0-9-]+)\.png$/)?.[1]
  } else if (code) {
    iso = code.toLowerCase()
  }
  if (!iso) return null
  const src = `https://flagcdn.com/w${cdn}/${iso}.png`
  return (
    <img
      src={src}
      alt={name ? `${name} flag` : "flag"}
      width={w}
      height={h}
      className={`${cls} border border-white/5 object-cover bg-slate-800 flex-shrink-0`}
    />
  )
}
