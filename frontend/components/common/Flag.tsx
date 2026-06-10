interface FlagProps {
  code?: string
  name: string
  size?: "sm" | "md" | "lg"
  url?: string
}

const SIZES = {
  sm: { w: 20, h: 14, cls: "rounded-sm" },
  md: { w: 32, h: 22, cls: "rounded" },
  lg: { w: 42, h: 30, cls: "rounded-md" },
}

export function Flag({ code, name, size = "md", url }: FlagProps) {
  const { w, h, cls } = SIZES[size]
  let src: string
  if (url) {
    const iso = url.match(/\/([a-z0-9-]+)\.png$/)?.[1]
    src = iso ? `https://flagcdn.com/w${w * 2}/${iso}.png` : url
  } else {
    src = `https://flagcdn.com/w${w * 2}/${code ?? ""}.png`
  }
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
