"use client"
import { useEffect, useState } from "react"
import { usePathname } from "next/navigation"

const TOUR_KEY = "wc26_tour_seen"
const TOUR_VERSION = "1"  // bump to re-show after major UI changes

interface Card {
  title: string
  body: string
  cta?: string
  href?: string
}

const CARDS: Card[] = [
  {
    title: "Welcome to WC26 Predictor",
    body: "Data-driven probabilities for every World Cup 2026 match, updated live. No fluff, no paywall.",
  },
  {
    title: "We score ourselves publicly",
    body: "Every pre-match probability is locked in, then graded against the result. The Report Card shows our hit rate, Brier, and how we compare to Opta and the bookmaker market.",
    cta: "See the scoreboard",
    href: "/performance",
  },
  {
    title: "Spot value bets",
    body: "Browse the Value Board for picks where the model thinks the bookmaker is offering too much. The bet builder lets you pressure-test your own slip with correlation-correct pricing.",
    cta: "Try the Value Board",
    href: "/value",
  },
  {
    title: "Want alerts?",
    body: "Push notifications fire when the model spots a big value pick or a live match swings hard. Tap the bell at the top once you're ready.",
    cta: "Got it",
  },
]

export function FirstVisitTour() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const [step, setStep] = useState(0)

  useEffect(() => {
    // Deep-linked users came for the page they clicked on — don't ambush them
    // with a welcome tour. Only fire on the homepage; if a user backs out to /
    // later, the tour kicks in there.
    if (pathname !== "/") return
    const stored = localStorage.getItem(TOUR_KEY)
    if (stored !== TOUR_VERSION) {
      const t = setTimeout(() => setOpen(true), 1200)
      return () => clearTimeout(t)
    }
  }, [pathname])

  const close = () => {
    setOpen(false)
    localStorage.setItem(TOUR_KEY, TOUR_VERSION)
  }

  if (!open) return null
  const card = CARDS[step]
  const isLast = step === CARDS.length - 1
  return (
    <div
      className="fixed inset-0 z-50 bg-surface-0/85 backdrop-blur-sm flex items-end sm:items-center justify-center p-3"
      role="dialog"
      aria-modal="true"
      onClick={(e) => {
        if (e.target === e.currentTarget) close()
      }}
    >
      <div className="w-full max-w-md rounded-2xl border border-edge bg-surface-1 shadow-2xl p-4 sm:p-6 animate-in fade-in slide-in-from-bottom-4">
        <div className="flex items-baseline justify-between mb-2">
          <p className="text-[10px] uppercase tracking-widest text-emerald-400 font-bold">
            {step + 1} of {CARDS.length}
          </p>
          <button
            onClick={close}
            className="text-slate-500 hover:text-slate-300 text-[16px] leading-none px-1.5 -mr-1.5"
            aria-label="Skip tour"
          >×</button>
        </div>
        <h2 className="font-display text-[20px] font-bold text-white leading-tight mb-2">{card.title}</h2>
        <p className="text-[13px] text-slate-300 leading-relaxed mb-5">{card.body}</p>
        <div className="flex items-center gap-2 justify-between">
          <div className="flex gap-1">
            {CARDS.map((_, i) => (
              <div
                key={i}
                className={`h-1.5 rounded-full transition-all ${i === step ? "w-6 bg-emerald-400" : "w-1.5 bg-slate-700"}`}
              />
            ))}
          </div>
          <div className="flex gap-2">
            {card.href ? (
              <a
                href={card.href}
                onClick={close}
                className="text-[12px] font-semibold text-emerald-300 hover:text-emerald-200 px-3 py-2"
              >
                {card.cta} →
              </a>
            ) : null}
            {isLast ? (
              <button
                onClick={close}
                className="text-[12px] font-bold px-4 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-400"
              >
                Start exploring
              </button>
            ) : (
              <button
                onClick={() => setStep((s) => s + 1)}
                className="text-[12px] font-bold px-4 py-2 rounded-lg bg-emerald-500 text-white hover:bg-emerald-400"
              >
                Next
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
