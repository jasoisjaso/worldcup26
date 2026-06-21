// Shared skeleton blocks for first-paint placeholders. Hand-rolled because the
// rest of the site uses zero external chart/UI libs and we want exactly one
// shimmer style site-wide.
//
// The shimmer is a CSS-only animation against the existing dark surface ramp:
// no extra JS, no layout shift when the real content replaces it.

import type { CSSProperties } from "react"

const shimmer: CSSProperties = {
  backgroundImage:
    "linear-gradient(90deg, rgba(255,255,255,0.04) 0%, rgba(255,255,255,0.08) 40%, rgba(255,255,255,0.04) 100%)",
  backgroundSize: "200% 100%",
  animation: "wc26-shimmer 1.6s linear infinite",
}

export function SkeletonBlock({
  className = "",
  style,
}: {
  className?: string
  style?: CSSProperties
}) {
  return (
    <div
      aria-hidden="true"
      className={`bg-surface-2 rounded ${className}`}
      style={{ ...shimmer, ...style }}
    />
  )
}

/** A card-shaped placeholder matching the dimensions of an opportunity / KPI card. */
export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="p-4 rounded-lg border border-edge bg-surface-1 space-y-3">
      <SkeletonBlock className="h-3 w-1/3" />
      <SkeletonBlock className="h-8 w-2/3" />
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBlock key={i} className="h-2 w-full" />
      ))}
    </div>
  )
}

/** Page-level skeleton: header strip + N card grid. */
export function SkeletonPage({
  title,
  cards = 6,
}: {
  title?: string
  cards?: number
}) {
  return (
    <div className="p-4 lg:p-6 max-w-6xl mx-auto">
      {title && <div className="mb-6 text-sm uppercase tracking-wider text-slate-500">{title}</div>}
      <div className="space-y-3 mb-6">
        <SkeletonBlock className="h-9 w-2/3 max-w-md" />
        <SkeletonBlock className="h-3 w-1/2 max-w-sm" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {Array.from({ length: cards }).map((_, i) => (
          <SkeletonCard key={i} />
        ))}
      </div>
    </div>
  )
}
