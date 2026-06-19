"use client"
/**
 * Miniature win-probability sparkline (20px tall, no labels) for the live card feed.
 */
const W = 120; const H = 20; const P = 2

export function MiniSparkline({ data }: { data: Array<{ e: number; h: number; a: number }> }) {
  if (data.length < 2) return <div className="w-[120px] h-[20px]" />
  const xMax = data[data.length - 1].e
  const xs = (e: number) => P + (e / xMax) * (W - 2 * P)
  const ys = (v: number) => P + (1 - v) * (H - 2 * P)
  let hPath = ""; let aPath = ""
  for (let i = 0; i < data.length; i++) {
    const { e, h, a } = data[i]
    const x = xs(e); const yh = ys(h); const ya = ys(a)
    hPath += `${i === 0 ? "M" : "L"} ${x} ${yh} `
    aPath += `${i === 0 ? "M" : "L"} ${x} ${ya} `
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-[120px] h-[20px] shrink-0" preserveAspectRatio="none">
      <path d={hPath} fill="none" stroke="#10b981" strokeWidth="1.5" strokeLinejoin="round" />
      <path d={aPath} fill="none" stroke="#fb923c" strokeWidth="1.5" strokeLinejoin="round" />
    </svg>
  )
}
