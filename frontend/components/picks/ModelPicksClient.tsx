"use client"
import { useEffect, useState } from "react"

interface Leg {
  leg_order: number
  match_id: string
  match_label: string
  kickoff_iso: string | null
  market: string
  market_label: string
  model_prob: number | null
  market_implied_prob: number | null
  book_odds: number | null
  book_name: string | null
  status: string
  actual_score: string | null
}

interface Multi {
  id: number
  generated_at: string | null
  label: string
  kind: "sgm" | "cross"
  combined_prob: number
  combined_fair_odds: number | null
  combined_book_odds: number
  ev_pct: number
  kelly_pct: number
  status: "pending" | "won" | "lost" | "void"
  settled_at: string | null
  profit_loss_units: number | null
  legs: Leg[]
}

interface Stats {
  total_settled: number
  won: number
  lost: number
  hit_rate_pct: number | null
  profit_loss_units: number
  roi_pct: number | null
}

interface Data {
  active: Multi[]
  recent: Multi[]
  stats: Stats
}

const TZ_KEY = "wc26_tz"
const DEFAULT_TZ = "Australia/Brisbane"

function pct(p: number | null | undefined, dp = 1): string {
  if (p == null || isNaN(p)) return "—"
  return `${(p * 100).toFixed(dp)}%`
}

function pickColor(status: string, isTop = false) {
  if (status === "won") return "border-emerald-700/40 bg-emerald-950/30"
  if (status === "lost") return "border-amber-700/40 bg-amber-950/20"
  if (status === "void") return "border-slate-700/50 bg-slate-900/40"
  // Pending — give the top pick a brighter edge so the eye lands there first.
  if (isTop) return "border-emerald-600/60 bg-emerald-950/20"
  return "border-edge bg-surface-2"
}

// Human label for a multi by leg count. Mirrors the doc — 2 = tight double,
// 3 = balanced treble, 4 = bold (rare).
function shapeLabel(kind: "sgm" | "cross", legs: number): string {
  if (kind === "sgm") {
    if (legs === 2) return "Same-game double"
    if (legs === 3) return "Same-game treble"
    return `Same-game ${legs}-leg`
  }
  if (legs === 2) return "Tight double"
  if (legs === 3) return "Balanced treble"
  if (legs === 4) return "Bold 4-fold"
  return `${legs}-leg multi`
}

function legStatusBadge(status: string) {
  if (status === "won") return <span className="text-[10px] font-bold text-emerald-400 ml-2">✓</span>
  if (status === "lost") return <span className="text-[10px] font-bold text-amber-400 ml-2">✗</span>
  return null
}

function MultiCard({ m, tz, isTop = false }: { m: Multi; tz: string; isTop?: boolean }) {
  const isPending = m.status === "pending"
  const won = m.status === "won"
  const stake = 10
  const returns = won ? (stake * m.combined_book_odds).toFixed(0) : null
  return (
    <div className={`rounded-2xl border shadow-e1 ${pickColor(m.status, isTop && isPending)} ${isTop && isPending ? "ring-1 ring-emerald-500/30" : ""}`}>
      {isTop && isPending && (
        <div className="px-4 pt-3 pb-1 flex items-center gap-2">
          <span className="text-[9px] font-bold uppercase tracking-widest bg-emerald-500/20 text-emerald-300 px-1.5 py-0.5 rounded">
            ★ Top pick
          </span>
          <span className="text-[10px] text-slate-500">Highest-confidence multi on the slate</span>
        </div>
      )}
      <div className="px-4 pt-3 pb-2 border-b border-edge/40 flex items-baseline justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
            {shapeLabel(m.kind, m.legs.length)}
          </p>
          <p className="text-[13px] text-slate-200 font-semibold truncate">{m.label}</p>
        </div>
        <div className="text-right shrink-0">
          {isPending ? (
            <p className="text-[10px] uppercase tracking-widest text-emerald-400/80">Active</p>
          ) : won ? (
            <p className="text-[10px] uppercase tracking-widest text-emerald-400">Won +{m.profit_loss_units?.toFixed(2)} units</p>
          ) : m.status === "lost" ? (
            <p className="text-[10px] uppercase tracking-widest text-amber-400">Lost</p>
          ) : (
            <p className="text-[10px] uppercase tracking-widest text-slate-500">Void</p>
          )}
        </div>
      </div>

      <ul className="divide-y divide-edge/20">
        {m.legs.map((leg) => {
          // Per-leg edge over the de-vigged market — surfaces which leg drives
          // the slip's value. A multi can look strong on combined EV but be
          // carried by one fluky leg; the chip makes that visible.
          const legEdge =
            leg.model_prob != null && leg.market_implied_prob != null && leg.market_implied_prob > 0
              ? leg.model_prob / leg.market_implied_prob - 1
              : null
          return (
            <li key={leg.leg_order} className="px-4 py-2.5">
              <div className="flex items-baseline justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-[11.5px] text-slate-300 font-semibold truncate">{leg.match_label}</p>
                  <p className="text-[11px] text-slate-400">
                    {leg.market_label}
                    {legStatusBadge(leg.status)}
                    {leg.actual_score && (
                      <span className="text-[10px] text-slate-500 ml-2 font-mono">{leg.actual_score}</span>
                    )}
                  </p>
                </div>
                <div className="text-right shrink-0">
                  {leg.book_odds && (
                    <p className="text-[12px] text-slate-200 font-mono">${leg.book_odds.toFixed(2)}</p>
                  )}
                  {leg.book_name && (
                    <p className="text-[9px] text-slate-600 uppercase">{leg.book_name}</p>
                  )}
                  {legEdge != null && (
                    <p className={`text-[10px] font-mono font-bold mt-0.5 ${legEdge >= 0.03 ? "text-emerald-400" : "text-slate-500"}`}>
                      {legEdge >= 0 ? "+" : ""}{(legEdge * 100).toFixed(1)}%
                    </p>
                  )}
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      <div className="px-4 py-3 border-t border-edge/40 grid grid-cols-3 gap-3 text-center">
        <div>
          <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Combined odds</p>
          <p className="font-mono tabular-nums text-[16px] font-bold text-slate-100">{m.combined_book_odds.toFixed(2)}</p>
        </div>
        <div>
          <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Win chance</p>
          <p className="font-mono tabular-nums text-[16px] font-bold text-emerald-400">{pct(m.combined_prob)}</p>
        </div>
        <div>
          <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Edge (EV)</p>
          <p className={`font-mono tabular-nums text-[16px] font-bold ${m.ev_pct >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
            {m.ev_pct >= 0 ? "+" : ""}{m.ev_pct.toFixed(1)}%
          </p>
        </div>
      </div>

      <div className="px-4 py-2 border-t border-edge/30 flex flex-wrap items-baseline justify-between gap-1">
        <p className="text-[10px] text-slate-500">
          Suggested stake: <span className="text-emerald-300 font-mono font-bold">{m.kelly_pct.toFixed(2)}%</span> of bankroll{" "}
          <span
            className="text-slate-600 cursor-help underline decoration-dotted underline-offset-2"
            title="Quarter-Kelly: a defensive fraction of the textbook optimal bet size. Plenty for real money."
          >
            (?)
          </span>
        </p>
        {isPending && m.legs[0]?.kickoff_iso && (
          <p className="text-[10px] text-slate-600" suppressHydrationWarning>
            First leg: {new Date(m.legs[0].kickoff_iso).toLocaleString("en-AU", { timeZone: tz, weekday: "short", hour: "2-digit", minute: "2-digit" })}
          </p>
        )}
        {!isPending && won && (
          <p className="text-[10px] text-emerald-300">$10 → ${returns}</p>
        )}
      </div>
    </div>
  )
}

export function ModelPicksClient({ initialData }: { initialData: Data }) {
  const [data, setData] = useState<Data>(initialData)
  const [tz, setTz] = useState(DEFAULT_TZ)

  useEffect(() => {
    setTz(localStorage.getItem(TZ_KEY) || DEFAULT_TZ)
    const onTz = (e: Event) => {
      const d = (e as CustomEvent).detail
      if (d?.tz) setTz(d.tz)
    }
    window.addEventListener("wc26_tz_change", onTz)
    const i = setInterval(async () => {
      try {
        const r = await fetch("/api/proxy/model-multis")
        const j = await r.json()
        setData(j)
      } catch { /* silent */ }
    }, 60_000)
    return () => {
      clearInterval(i)
      window.removeEventListener("wc26_tz_change", onTz)
    }
  }, [])

  const { active, recent, stats } = data

  return (
    <div className="space-y-5">
      {/* Stats strip */}
      <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2">Track record</p>
        {stats.total_settled === 0 ? (
          <p className="text-[12px] text-slate-400 leading-snug">
            No multis have settled yet. First batch goes live ahead of today&apos;s matches. Check back after kickoff.
          </p>
        ) : (
          <div className="grid grid-cols-4 gap-3 text-center">
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Settled</p>
              <p className="font-mono tabular-nums text-[18px] font-bold text-slate-100">{stats.total_settled}</p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">Hit rate</p>
              <p className="font-mono tabular-nums text-[18px] font-bold text-emerald-400">
                {stats.hit_rate_pct != null ? `${stats.hit_rate_pct.toFixed(1)}%` : "—"}
              </p>
              <p className="text-[9.5px] text-slate-500">{stats.won}W · {stats.lost}L</p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">P/L (units)</p>
              <p className={`font-mono tabular-nums text-[18px] font-bold ${stats.profit_loss_units >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                {stats.profit_loss_units >= 0 ? "+" : ""}{stats.profit_loss_units.toFixed(2)}
              </p>
            </div>
            <div>
              <p className="text-[9.5px] uppercase tracking-widest text-slate-600">ROI</p>
              <p className={`font-mono tabular-nums text-[18px] font-bold ${(stats.roi_pct ?? 0) >= 0 ? "text-emerald-400" : "text-amber-400"}`}>
                {stats.roi_pct != null ? `${stats.roi_pct >= 0 ? "+" : ""}${stats.roi_pct.toFixed(1)}%` : "—"}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Active — ranked so the highest-EV pick is the badged "Top pick". The
          picker scores by joint_prob * ln(1+edge) * CLV bias, and ev_pct is
          the closest user-facing proxy for that score, so we sort on it. */}
      <div>
        <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 font-bold">
          Active picks ({active.length})
        </p>
        {active.length === 0 ? (
          <div className="rounded-xl border border-edge bg-surface-2 p-4 text-[12px] text-slate-400 leading-snug">
            Nothing active right now. New balanced multis get auto-picked when there are upcoming matches with enough edge.
          </div>
        ) : (
          <div className="space-y-3">
            {[...active].sort((a, b) => b.ev_pct - a.ev_pct).map((m, i) =>
              <MultiCard key={m.id} m={m} tz={tz} isTop={i === 0} />
            )}
          </div>
        )}
      </div>

      {/* Recent */}
      {recent.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-widest text-slate-500 mb-2 font-bold">
            Recent results
          </p>
          <div className="space-y-3">
            {recent.map((m) => <MultiCard key={m.id} m={m} tz={tz} />)}
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600 leading-snug px-1">
        Picks are auto-generated by the model when it sees an edge against best-available bookmaker pricing.
        Each pick is graded once all legs settle. P/L assumes a flat 1-unit stake per pick.
        Multis lose most of the time. Stake small (quarter-Kelly or less). 18+ only.
      </p>
    </div>
  )
}
