"use client"

import { useEffect } from "react"

export default function Error({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    // Surfaced in the browser console for debugging; no PII is logged.
    console.error(error)
  }, [error])

  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center px-6 text-center">
      <p className="font-mono text-sm text-emerald-400 tracking-widest uppercase">Something broke</p>
      <h1 className="mt-3 text-2xl md:text-3xl font-display font-bold text-white">
        We could not load that
      </h1>
      <p className="mt-2 max-w-md text-sm text-slate-400 leading-relaxed">
        The model or odds feed did not respond in time. This is usually momentary.
        Try again, and if it keeps happening the data feed may be refreshing.
      </p>
      <button
        onClick={reset}
        className="mt-6 rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-surface-0 transition-colors hover:bg-emerald-400 active:scale-[0.98]"
      >
        Try again
      </button>
    </div>
  )
}
