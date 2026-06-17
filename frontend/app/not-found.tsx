import Link from "next/link"

export default function NotFound() {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center px-6 text-center">
      <p className="font-mono text-sm text-emerald-400 tracking-widest uppercase">404</p>
      <h1 className="mt-3 text-2xl md:text-3xl font-display font-bold text-white">
        That page is off the pitch
      </h1>
      <p className="mt-2 max-w-md text-sm text-slate-400 leading-relaxed">
        The match or page you were after does not exist. It may have been a knockout
        fixture that has not been drawn yet.
      </p>
      <div className="mt-6 flex flex-wrap items-center justify-center gap-3">
        <Link
          href="/"
          className="rounded-lg bg-emerald-500 px-4 py-2 text-sm font-semibold text-surface-0 transition-colors hover:bg-emerald-400"
        >
          Back to matches
        </Link>
        <Link
          href="/winner"
          className="rounded-lg border border-edge px-4 py-2 text-sm font-medium text-slate-300 transition-colors hover:border-edge-strong hover:text-white"
        >
          World Cup odds
        </Link>
      </div>
    </div>
  )
}
