import Link from "next/link"

export function Footer() {
  return (
    <footer className="border-t border-edge mt-10 px-5 py-6 text-center">
      <p className="text-[11px] text-slate-500 max-w-xl mx-auto leading-relaxed">
        Model estimates, not guarantees. A strong edge can still lose. For 18+ only.
        Bet only what you can afford to lose, and take a break if it stops being fun.
      </p>
      <div className="flex flex-wrap items-center justify-center gap-x-4 gap-y-1.5 mt-3 text-[11px] text-slate-600">
        <Link href="/bracket" className="hover:text-emerald-400 transition-colors">Bracket</Link>
        <Link href="/value" className="hover:text-emerald-400 transition-colors">Value board</Link>
        <Link href="/acca" className="hover:text-emerald-400 transition-colors">Acca builder</Link>
        <Link href="/how-it-works" className="hover:text-emerald-400 transition-colors">How it works</Link>
        <Link href="/performance" className="hover:text-emerald-400 transition-colors">Track record</Link>
        <span className="text-slate-700">WC2026 Predictor</span>
      </div>
    </footer>
  )
}
