"use client"
import { useEffect, useMemo, useRef, useState } from "react"
import { api } from "@/lib/api"
import type {
  Match,
  MultiAnalysis,
  MultiLegInput,
  MultiAnalysisLeg,
} from "@/lib/types"

type MarketChoice = { value: string; label: string }
type MarketGroup = { label: string; options: MarketChoice[] }

// Static catalog of the markets a punter can put in a leg. Mirrors the backend
// MARKET_CATALOG (multi_analyzer.py) so the picker never offers something the
// analyzer cannot price off the score grid.
const MARKET_GROUPS: MarketGroup[] = [
  {
    label: "Match result",
    options: [
      { value: "home_win", label: "Home win" },
      { value: "draw",     label: "Draw" },
      { value: "away_win", label: "Away win" },
    ],
  },
  {
    label: "Double chance",
    options: [
      { value: "1x", label: "Home or draw (1X)" },
      { value: "x2", label: "Draw or away (X2)" },
      { value: "12", label: "Home or away (12)" },
    ],
  },
  {
    label: "Total goals",
    options: [
      { value: "over_1_5",   label: "Over 1.5 goals" },
      { value: "over_2_5",   label: "Over 2.5 goals" },
      { value: "over_3_5",   label: "Over 3.5 goals" },
      { value: "under_2_5",  label: "Under 2.5 goals" },
      { value: "under_3_5",  label: "Under 3.5 goals" },
      { value: "under_4_5",  label: "Under 4.5 goals" },
    ],
  },
  {
    label: "Goal bands",
    options: [
      { value: "goals_1_to_3", label: "1 to 3 goals" },
      { value: "goals_2_to_4", label: "2 to 4 goals" },
      { value: "goals_3_to_5", label: "3 to 5 goals" },
    ],
  },
  {
    label: "Both teams to score + clean sheets",
    options: [
      { value: "btts",             label: "Both teams to score" },
      { value: "btts_no",          label: "Both teams to score: no" },
      { value: "home_clean_sheet", label: "Home clean sheet" },
      { value: "away_clean_sheet", label: "Away clean sheet" },
    ],
  },
]

function teamSubstitutedLabel(label: string, match?: Match): string {
  if (!match) return label
  return label
    .replace("Home win", `${match.home.name} win`)
    .replace("Home or draw", `${match.home.name} or draw`)
    .replace("Home or away", `${match.home.name} or ${match.away.name}`)
    .replace("Home clean sheet", `${match.home.name} clean sheet`)
    .replace("Draw or away", `Draw or ${match.away.name}`)
    .replace("Away win", `${match.away.name} win`)
    .replace("Away clean sheet", `${match.away.name} clean sheet`)
}

interface DraftLeg {
  id: string                   // stable client-side id for React keys
  match_id: string | null
  market: string
  book_price: string           // raw input
}

const newDraft = (): DraftLeg => ({
  id: Math.random().toString(36).slice(2),
  match_id: null,
  market: "over_1_5",
  book_price: "",
})

function pctFmt(p: number | null | undefined, digits = 1): string {
  if (p == null || isNaN(p)) return "—"
  return `${(p * 100).toFixed(digits)}%`
}

function pricePct(book: string): number | null {
  const n = parseFloat(book)
  if (isNaN(n) || n <= 1.0) return null
  return 1.0 / n
}

function evClass(ev: number | null | undefined): string {
  if (ev == null || isNaN(ev)) return "text-slate-300"
  if (ev >= 0.05) return "text-emerald-400"
  if (ev > 0) return "text-emerald-500"
  if (ev > -0.02) return "text-slate-300"
  return "text-amber-500"
}

function edgeChipFor(flag: MultiAnalysisLeg["edge_flag"]): { text: string; cls: string } {
  if (flag === "edge")     return { text: "EDGE",      cls: "bg-emerald-900/40 text-emerald-300 border-emerald-700/50" }
  if (flag === "anti_edge") return { text: "MODEL DISLIKES", cls: "bg-amber-900/40 text-amber-300 border-amber-700/50" }
  if (flag === "no_edge")  return { text: "NO EDGE",   cls: "bg-slate-800 text-slate-400 border-edge" }
  return { text: "EDGE UNKNOWN", cls: "bg-slate-900 text-slate-500 border-edge" }
}

/** Single-bar edge gauge: model% vs market-implied%. */
function EdgeBar({ model, market }: { model: number | null; market: number | null }) {
  const mPct = model != null ? Math.round(model * 100) : null
  const bPct = market != null ? Math.round(market * 100) : null
  if (mPct == null) return null
  const lo = bPct != null ? Math.min(mPct, bPct) : mPct
  const hi = bPct != null ? Math.max(mPct, bPct) : mPct
  const win = bPct != null ? mPct >= bPct : true
  return (
    <div>
      <div className="relative h-4 rounded bg-surface-1 overflow-hidden border border-edge">
        <div
          className={`absolute inset-y-0 ${win ? "bg-emerald-500/30" : "bg-amber-500/30"}`}
          style={{ left: `${lo}%`, width: `${Math.max(1, hi - lo)}%` }}
        />
        {bPct != null && (
          <div className="absolute inset-y-0 w-[2px] bg-slate-400" style={{ left: `${bPct}%` }} />
        )}
        <div className="absolute inset-y-0 w-[2px] bg-emerald-400" style={{ left: `${mPct}%` }} />
      </div>
      <div className="flex justify-between text-[10px] mt-0.5">
        <span className="text-slate-500">Bookie de-vigged{" "}
          <span className="font-mono text-slate-300">{bPct != null ? `${bPct}%` : "—"}</span></span>
        <span className="text-slate-500">Model{" "}
          <span className="font-mono text-emerald-400 font-bold">{mPct}%</span></span>
      </div>
    </div>
  )
}

/** Running combined-probability bar: shows how each successive leg shrinks the slip's
 * chance of landing. Same data the model uses to price the slip. */
function LegImpactBar({ analysis }: { analysis: MultiAnalysis }) {
  // Group legs by match so the same-match joint contributes once (the spec is clear
  // that within-match legs are NOT independent and we shouldn't fake an extra step).
  const byMatch = new Map<string, MultiAnalysisLeg[]>()
  analysis.legs.forEach((l) => {
    const arr = byMatch.get(l.match_id) ?? []
    arr.push(l)
    byMatch.set(l.match_id, arr)
  })
  const steps: { label: string; p_step: number; p_running: number }[] = []
  let running = 1.0
  for (const pm of analysis.per_match) {
    const p_step = pm.joint_prob_from_grid
    running *= p_step
    const legs = byMatch.get(pm.match_id) ?? []
    const matchLabel = legs[0]?.match_label ?? pm.match_id
    const legLabels = legs.map((l) => l.label).join(" + ")
    steps.push({
      label: `${matchLabel}: ${legLabels}`,
      p_step,
      p_running: running,
    })
  }
  if (steps.length === 0) return null
  const W = 320, H = 100, padL = 8, padR = 8, padT = 6, padB = 18
  const barW = (W - padL - padR) / steps.length

  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-3.5">
      <p className="text-[11px] font-bold text-slate-300 mb-0.5">
        How each leg moves your win chance
      </p>
      <p className="text-[10.5px] text-slate-500 leading-snug mb-2">
        Starts at 100%. Each match multiplies it. Same-match legs share a single bar
        — they correlate, so the model prices them as one joint.
      </p>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full max-w-[420px]" role="img"
        aria-label="Running combined-probability bar">
        {steps.map((s, i) => {
          const x = padL + i * barW
          const h = (s.p_running) * (H - padT - padB)
          return (
            <g key={i}>
              <rect x={x + 2} y={H - padB - h} width={barW - 4} height={h}
                fill="#10b981" opacity={0.85} />
              <text x={x + barW / 2} y={H - 6} textAnchor="middle"
                fontSize="9.5" fill="#94a3b8" fontWeight="600">
                {Math.round(s.p_running * 100)}%
              </text>
            </g>
          )
        })}
      </svg>
      <ul className="mt-2 space-y-1 text-[10.5px] text-slate-400">
        {steps.map((s, i) => (
          <li key={i} className="flex items-baseline justify-between gap-2">
            <span className="truncate">{s.label}</span>
            <span className="font-mono text-slate-300 shrink-0">
              ×{s.p_step.toFixed(3)} → <span className="text-emerald-400 font-bold">{Math.round(s.p_running * 100)}%</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

/** Kelly-criterion stake suggestion for the slip.
 * Full Kelly is the variance-blind mathematically optimal bet size (assumes the
 * model's probability is exactly right). Quarter Kelly is the defensive default
 * — it caps drawdowns when the model is slightly off. We never show "stake X
 * dollars" because we don't know the user's bankroll; we show "% of bankroll". */
function KellyStakeCard({ analysis }: { analysis: MultiAnalysis }) {
  const p = analysis.combined_probability
  // Use the bookmaker's slip price if entered; otherwise model fair odds (which
  // gives a Kelly of 0 since EV = 0). The latter is honest about the slip having
  // no edge at fair odds — there's no point sizing a Kelly stake on a 0% edge.
  const odds = analysis.slip_book_price ?? analysis.fair_combined_odds
  if (p == null || odds == null || odds <= 1.01 || p <= 0) return null

  const b = odds - 1
  const q = 1 - p
  const fullKellyRaw = (b * p - q) / b
  const fullKelly = Math.max(0, fullKellyRaw)
  const quarterKelly = fullKelly / 4
  const isEdge = fullKellyRaw > 0
  const isUsingBookPrice = analysis.slip_book_price != null

  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-3.5">
      <p className="text-[11px] font-bold text-slate-300 mb-1">
        Kelly stake suggestion
      </p>
      <p className="text-[10.5px] text-slate-500 mb-3 leading-snug">
        {isEdge
          ? "If the model is right, this is the bankroll fraction that maximises growth over time. Quarter Kelly is the safer default — it cuts variance hard."
          : isUsingBookPrice
            ? "No mathematical edge at the offered price — Kelly says don't stake on this slip."
            : "Enter the bookie's slip price above to see a Kelly stake size."}
      </p>
      {isEdge ? (
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-lg border border-edge bg-surface-1 px-3 py-2.5">
            <p className="text-[9.5px] font-bold uppercase tracking-wider text-amber-400/80">
              Full Kelly (aggressive)
            </p>
            <p className="font-mono tabular-nums text-[20px] font-bold text-amber-300 mt-0.5">
              {(fullKelly * 100).toFixed(2)}%
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">of bankroll</p>
          </div>
          <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/30 px-3 py-2.5">
            <p className="text-[9.5px] font-bold uppercase tracking-wider text-emerald-400/90">
              Quarter Kelly (recommended)
            </p>
            <p className="font-mono tabular-nums text-[20px] font-bold text-emerald-300 mt-0.5">
              {(quarterKelly * 100).toFixed(2)}%
            </p>
            <p className="text-[10px] text-slate-500 mt-0.5">of bankroll</p>
          </div>
        </div>
      ) : (
        <div className="rounded-lg border border-slate-700/50 bg-slate-900/40 px-3 py-2.5 text-center">
          <p className="font-mono text-[18px] font-bold text-slate-400">0.00%</p>
          <p className="text-[10px] text-slate-500 mt-0.5">no Kelly stake</p>
        </div>
      )}
      <p className="text-[10px] text-slate-600 mt-2 leading-snug">
        Multis go down. Even with edge, expect long losing runs. Never stake more
        than Full Kelly suggests, and Quarter Kelly is plenty for any real-money
        play.
      </p>
    </div>
  )
}


/** Tiny bankroll-outcome panel for the slip: this is a single binary bet, so the
 * distribution is two bars (lose stake / win stake * odds-1). Honest about that. */
function BankrollOutcome({
  analysis, stakePctOfBank,
}: { analysis: MultiAnalysis; stakePctOfBank: number }) {
  const p = analysis.combined_probability ?? 0
  const odds = analysis.slip_book_price ?? analysis.fair_combined_odds ?? 0
  const ev = analysis.ev
  if (!p || !odds) return null

  const winFrac = stakePctOfBank * (odds - 1)
  const lossFrac = -stakePctOfBank
  const W = 320, H = 80
  const lo = lossFrac
  const hi = winFrac
  const span = hi - lo || 1
  const zeroX = ((0 - lo) / span) * (W - 16) + 8
  const lossW = ((0 - lo) / span) * (W - 16)
  const winW = ((hi - 0) / span) * (W - 16)
  const lossH = (1 - p) * 60 + 8
  const winH = p * 60 + 8

  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-3.5">
      <p className="text-[11px] font-bold text-slate-300 mb-1">
        Outcome if you stake {(stakePctOfBank * 100).toFixed(1)}% of bankroll
      </p>
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="w-full max-w-[420px]" role="img"
        aria-label="Bankroll outcome distribution">
        {/* loss bar (left of break-even) */}
        <rect x={8} y={H - lossH} width={lossW} height={lossH} fill="#f59e0b" opacity={0.85} />
        {/* win bar (right of break-even) */}
        <rect x={zeroX} y={H - winH} width={winW} height={winH} fill="#10b981" opacity={0.85} />
        {/* break-even line */}
        <line x1={zeroX} y1={0} x2={zeroX} y2={H} stroke="#64748b" strokeWidth="1" strokeDasharray="3 3" />
        <text x={zeroX} y={H + 12} textAnchor="middle" fill="#64748b" fontSize="9">break even</text>
        <text x={(8 + zeroX) / 2} y={H - lossH - 4} textAnchor="middle"
          fill="#fbbf24" fontSize="10" fontWeight="600">
          lose {Math.round((1 - p) * 100)}%
        </text>
        <text x={(zeroX + W - 8) / 2} y={H - winH - 4} textAnchor="middle"
          fill="#34d399" fontSize="10" fontWeight="600">
          win {Math.round(p * 100)}%
        </text>
      </svg>
      <p className="text-[10.5px] text-slate-500 mt-1 leading-snug">
        Expected return per ${(stakePctOfBank * 100).toFixed(1)}-unit stake:{" "}
        <span className={`font-mono font-bold ${evClass(ev)}`}>
          {ev != null ? `${ev >= 0 ? "+" : ""}${(ev * stakePctOfBank * 100).toFixed(2)}%`
                       : "enter a slip price for EV"}
        </span>
        . A multi loses most of the time. Stake small.
      </p>
    </div>
  )
}

type Objective = "solid" | "balanced" | "bold"

const OBJECTIVE_OPTIONS: { v: Objective; label: string; sub: string }[] = [
  { v: "solid",    label: "Most likely to land", sub: "Plays it safe" },
  { v: "balanced", label: "Best risk/reward",     sub: "Recommended" },
  { v: "bold",     label: "Long-shot value",      sub: "Bigger payouts" },
]

type BestPrice = { best_price: number | null; best_book: string | null }
type BestPricesByMatch = Record<string, Record<string, BestPrice>>

// Curated quick-start templates. Each one builds a 2-leg slip on the upcoming
// match the user picks. Designed to cover the most-asked-for shapes so first-
// time users skip the cold-start dropdown maze.
type Template = { label: string; sub: string; markets: [string, string] }
const SLIP_TEMPLATES: Template[] = [
  { label: "Goals + BTTS",      sub: "Both score + over 2.5",      markets: ["btts", "over_2_5"] },
  { label: "Home + goals",      sub: "Home win + over 1.5",        markets: ["home_win", "over_1_5"] },
  { label: "Away + goals",      sub: "Away win + over 1.5",        markets: ["away_win", "over_1_5"] },
  { label: "Defensive",         sub: "Under 2.5 + no BTTS",        markets: ["under_2_5", "btts_no"] },
  { label: "Open match",        sub: "Both score + 2 to 4 goals",  markets: ["btts", "goals_2_to_4"] },
  { label: "Safety net",        sub: "Home or draw + over 1.5",    markets: ["1x", "over_1_5"] },
]

// Smart paste parser. Looks for patterns like "<text> @ 1.85" or "<text> at 1.85"
// or "<text> ($1.85)". Returns up to N candidates with best-effort label cleanup.
type Parsed = { label: string; price: number }
function parsePastedSlip(raw: string, max = 8): Parsed[] {
  const out: Parsed[] = []
  // Split on common delimiters that betslips use
  const chunks = raw.split(/\r?\n|;|, +/).map((s) => s.trim()).filter(Boolean)
  const re = /(.+?)[ ]*(?:@|at|\$|\()[ ]*(\d+(?:\.\d{1,2})?)\)?\s*$/i
  for (const chunk of chunks) {
    const m = chunk.match(re)
    if (!m) continue
    const label = m[1].trim().replace(/[-—–:]+$/, "").trim()
    const price = parseFloat(m[2])
    if (!label || !price || price <= 1) continue
    out.push({ label, price })
    if (out.length >= max) break
  }
  return out
}

export function MultiBuilder({ matches }: { matches: Match[] }) {
  const [legs, setLegs] = useState<DraftLeg[]>([newDraft(), newDraft()])
  const [slipBookPrice, setSlipBookPrice] = useState<string>("")
  const [objective, setObjective] = useState<Objective>("balanced")
  const [analysis, setAnalysis] = useState<MultiAnalysis | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [bestPrices, setBestPrices] = useState<BestPricesByMatch>({})

  const matchById = useMemo(() => {
    const map = new Map<string, Match>()
    for (const m of matches) map.set(m.id, m)
    return map
  }, [matches])

  // Stable serialised input for the debounce dep.
  const inputKey = useMemo(() => JSON.stringify({
    legs: legs.map((l) => ({ m: l.match_id, k: l.market, p: l.book_price })),
    s: slipBookPrice, o: objective,
  }), [legs, slipBookPrice, objective])

  const abortRef = useRef<AbortController | null>(null)

  useEffect(() => {
    const usable: MultiLegInput[] = legs
      .filter((l) => l.match_id)
      .map((l) => ({
        match_id: l.match_id!,
        market: l.market,
        book_price: l.book_price ? parseFloat(l.book_price) : null,
      }))
    if (usable.length === 0) {
      setAnalysis(null); setError(null); return
    }

    abortRef.current?.abort()
    const ctl = new AbortController()
    abortRef.current = ctl
    const t = setTimeout(async () => {
      setLoading(true)
      try {
        const slipPrice = slipBookPrice ? parseFloat(slipBookPrice) : null
        const res = await api.analyzeMulti(usable, {
          slip_book_price: slipPrice && !isNaN(slipPrice) && slipPrice > 1 ? slipPrice : null,
          objective,
        })
        if (ctl.signal.aborted) return
        if (res.error) { setError(res.error); setAnalysis(null) }
        else { setError(null); setAnalysis(res) }
      } catch (e) {
        if (!ctl.signal.aborted) setError((e as Error).message)
      } finally {
        if (!ctl.signal.aborted) setLoading(false)
      }
    }, 300)
    return () => { clearTimeout(t); ctl.abort() }
  }, [inputKey])  // eslint-disable-line react-hooks/exhaustive-deps

  const updateLeg = (id: string, patch: Partial<DraftLeg>) => {
    setLegs((ls) => ls.map((l) => (l.id === id ? { ...l, ...patch } : l)))
  }
  const removeLeg = (id: string) => {
    setLegs((ls) => (ls.length > 1 ? ls.filter((l) => l.id !== id) : ls))
  }
  const addLeg = () => setLegs((ls) => [...ls, newDraft()])

  const applySuggestion = () => {
    if (!analysis?.suggestion?.new_legs) return
    setLegs(analysis.suggestion.new_legs.map((l, i) => ({
      id: `${Date.now()}-${i}`,
      match_id: l.match_id,
      market: l.market,
      book_price: "",
    })))
  }

  // Fetch best bookmaker prices whenever the set of selected matches changes.
  // Debounced so rapid edits don't spam the proxy.
  const selectedMatchIds = useMemo(
    () => Array.from(new Set(legs.map((l) => l.match_id).filter((x): x is string => !!x))),
    [legs],
  )
  const selectedKey = useMemo(() => selectedMatchIds.sort().join(","), [selectedMatchIds])

  useEffect(() => {
    if (selectedMatchIds.length === 0) {
      setBestPrices({})
      return
    }
    const ctl = new AbortController()
    const t = setTimeout(async () => {
      try {
        const r = await api.bestPrices(selectedMatchIds)
        if (!ctl.signal.aborted) setBestPrices(r.by_match ?? {})
      } catch { /* silent */ }
    }, 250)
    return () => { clearTimeout(t); ctl.abort() }
  }, [selectedKey])  // eslint-disable-line react-hooks/exhaustive-deps

  // Fill a leg's bookie price from the current best available book.
  const useBestPriceFor = (legId: string) => {
    const leg = legs.find((l) => l.id === legId)
    if (!leg?.match_id) return
    const bp = bestPrices[leg.match_id]?.[leg.market]?.best_price
    if (bp != null) updateLeg(legId, { book_price: bp.toFixed(2) })
  }

  // Apply a slip template to a specific match. Replaces all current legs with
  // the template's two markets on that one match.
  const applyTemplate = (template: Template, matchId: string) => {
    setLegs(template.markets.map((mkt, i) => ({
      id: `${Date.now()}-${i}`,
      match_id: matchId,
      market: mkt,
      book_price: "",
    })))
  }

  // Smart-paste handler. Parses pasted text into draft legs. Matches are NOT
  // automatically resolved (we'd need a fuzzy team-name matcher); the user
  // assigns a match per leg after paste. Price comes through immediately.
  const [pasteOpen, setPasteOpen] = useState(false)
  const [pasteText, setPasteText] = useState("")
  const [pasteFeedback, setPasteFeedback] = useState<string | null>(null)
  const handlePaste = () => {
    const parsed = parsePastedSlip(pasteText)
    if (parsed.length === 0) {
      setPasteFeedback("No prices spotted. Format each leg like 'Brazil to win @ 1.80' on a new line.")
      return
    }
    setLegs(parsed.map((p, i) => ({
      id: `${Date.now()}-${i}`,
      match_id: null,
      market: "over_1_5",  // user picks the right market — paste only gives label hints
      book_price: p.price.toFixed(2),
    })))
    setPasteFeedback(`${parsed.length} leg${parsed.length === 1 ? "" : "s"} added. Pick the match + market for each — your prices came through.`)
    setTimeout(() => { setPasteOpen(false); setPasteText(""); setPasteFeedback(null) }, 1500)
  }

  return (
    <div className="space-y-4">
      <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-4 py-3 text-[12px] text-slate-400 leading-relaxed">
        Pick any legs across any matches. Same-match legs go through the score grid
        (so the correlation is priced correctly, not assumed away). Drop in your bookmaker&apos;s
        price for the whole multi to see the model&apos;s EV.
      </div>

      {/* Objective toggle — three modes, stacks on small screens, default Balanced */}
      <div>
        <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">
          Optimize for
        </p>
        <div className="grid grid-cols-3 gap-1.5 sm:gap-2">
          {OBJECTIVE_OPTIONS.map((opt) => {
            const active = objective === opt.v
            return (
              <button
                key={opt.v}
                onClick={() => setObjective(opt.v)}
                className={[
                  "rounded-lg border px-2 py-2 text-left transition-colors",
                  active
                    ? "bg-emerald-900/40 border-emerald-700 text-emerald-200"
                    : "bg-surface-2 border-edge text-slate-400 hover:text-slate-200 hover:border-edge-strong",
                ].join(" ")}
              >
                <p className="text-[11px] sm:text-[12px] font-bold leading-tight">{opt.label}</p>
                <p className={`text-[9.5px] sm:text-[10px] mt-0.5 ${active ? "text-emerald-400/70" : "text-slate-600"}`}>
                  {opt.sub}
                </p>
              </button>
            )
          })}
        </div>
      </div>
      {/* Quick-start: templates + smart paste */}
      <div className="rounded-xl border border-edge bg-surface-2 p-3 sm:p-4 space-y-3">
        <div className="flex items-baseline justify-between gap-2">
          <p className="text-[11px] font-bold text-slate-300">Quick start</p>
          <button
            onClick={() => setPasteOpen((v) => !v)}
            className="text-[10.5px] font-semibold text-emerald-400 hover:text-emerald-300"
          >
            {pasteOpen ? "Hide paste" : "Paste from bookie →"}
          </button>
        </div>

        {/* Templates row — pick a match then apply */}
        <div>
          <p className="text-[9.5px] uppercase tracking-widest text-slate-600 mb-1.5">
            Common shapes (applies to one match)
          </p>
          <div className="flex flex-wrap gap-1.5">
            {SLIP_TEMPLATES.map((t) => (
              <button
                key={t.label}
                onClick={() => {
                  const target = legs.find((l) => l.match_id)?.match_id ?? matches[0]?.id
                  if (target) applyTemplate(t, target)
                }}
                disabled={!matches.length}
                className="text-left rounded-md border border-edge bg-surface-1 hover:bg-surface-0 hover:border-edge-strong px-2.5 py-1.5 disabled:opacity-40"
                title={t.sub}
              >
                <p className="text-[11.5px] text-slate-200 font-semibold leading-tight">{t.label}</p>
                <p className="text-[9.5px] text-slate-500 leading-tight">{t.sub}</p>
              </button>
            ))}
          </div>
          <p className="text-[10px] text-slate-600 mt-1.5">
            Applies to the first leg&apos;s match — change the match on either leg after.
          </p>
        </div>

        {/* Smart paste — collapsible */}
        {pasteOpen && (
          <div className="rounded-lg border border-emerald-700/40 bg-emerald-950/20 p-3 space-y-2">
            <p className="text-[10.5px] text-emerald-300/90 leading-snug">
              Paste your slip from any bookie. We&apos;ll extract each leg&apos;s price.
              Then assign a match + market for each.
            </p>
            <textarea
              value={pasteText}
              onChange={(e) => setPasteText(e.target.value)}
              rows={4}
              placeholder={"Brazil to win @ 1.80\nOver 2.5 goals @ 1.90\nBoth teams to score @ 1.65"}
              className="w-full bg-surface-0 border border-edge rounded-md px-2.5 py-2 text-[12px] text-slate-100 font-mono leading-snug min-h-[80px]"
            />
            <div className="flex items-center gap-2">
              <button
                onClick={handlePaste}
                className="px-3 py-1.5 rounded-md text-[11px] font-semibold bg-emerald-700 text-white hover:bg-emerald-600"
              >
                Extract legs
              </button>
              {pasteFeedback && (
                <p className="text-[10.5px] text-slate-300 leading-snug">{pasteFeedback}</p>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Slip composer — mobile-first leg cards (no more cramped 12-col grid) */}
      <div className="rounded-xl border border-edge bg-surface-2 p-3 sm:p-4">
        <p className="text-[11px] font-bold text-slate-300 mb-2.5">Your legs</p>
        <div className="space-y-2.5">
          {legs.map((leg, idx) => {
            const match = leg.match_id ? matchById.get(leg.match_id) : undefined
            const matchPrices = leg.match_id ? bestPrices[leg.match_id] : undefined
            const currentBest = matchPrices?.[leg.market]?.best_price
            const currentBook = matchPrices?.[leg.market]?.best_book
            return (
              <div
                key={leg.id}
                className="rounded-lg border border-edge bg-surface-1 p-3 space-y-2.5"
              >
                {/* Header row: leg # + remove button */}
                <div className="flex items-center justify-between">
                  <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500">
                    Leg {idx + 1}
                  </span>
                  <button
                    onClick={() => removeLeg(leg.id)}
                    disabled={legs.length <= 1}
                    className="text-slate-500 hover:text-amber-400 disabled:opacity-30 disabled:cursor-not-allowed text-[18px] leading-none px-1.5 -my-1 -mr-1.5"
                    title="Remove leg"
                    aria-label="Remove leg"
                  >×</button>
                </div>

                {/* Match selector — full width on mobile, half on desktop */}
                <div className="grid sm:grid-cols-2 gap-2">
                  <select
                    value={leg.match_id ?? ""}
                    onChange={(e) => updateLeg(leg.id, { match_id: e.target.value || null })}
                    className="bg-surface-0 border border-edge rounded-md px-2.5 py-2 text-[13px] text-slate-100 min-h-[36px]"
                  >
                    <option value="">— pick a match —</option>
                    {matches.map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.home.name} vs {m.away.name} · MD{m.matchday}
                      </option>
                    ))}
                  </select>
                  <select
                    value={leg.market}
                    onChange={(e) => updateLeg(leg.id, { market: e.target.value })}
                    className="bg-surface-0 border border-edge rounded-md px-2.5 py-2 text-[13px] text-slate-100 min-h-[36px]"
                  >
                    {MARKET_GROUPS.map((g) => (
                      <optgroup key={g.label} label={g.label}>
                        {g.options.map((opt) => {
                          const bp = matchPrices?.[opt.value]?.best_price
                          const suffix = bp != null ? ` · best $${bp.toFixed(2)}` : ""
                          return (
                            <option key={opt.value} value={opt.value}>
                              {teamSubstitutedLabel(opt.label, match)}{suffix}
                            </option>
                          )
                        })}
                      </optgroup>
                    ))}
                  </select>
                </div>

                {/* Bookie price input — own row so it's not cramped */}
                <div className="flex flex-wrap items-center gap-2">
                  <label className="text-[10px] font-bold uppercase tracking-widest text-slate-600 shrink-0 w-[68px] sm:w-auto">
                    Your odds
                  </label>
                  <input
                    inputMode="decimal"
                    value={leg.book_price}
                    onChange={(e) => updateLeg(leg.id, { book_price: e.target.value })}
                    placeholder="e.g. 1.85"
                    className="bg-surface-0 border border-edge rounded-md px-2.5 py-1.5 text-[13px] text-slate-100 font-mono text-center min-h-[34px] w-24"
                    title="Your bookmaker's price for this single leg"
                  />
                  {currentBest != null ? (
                    <button
                      onClick={() => useBestPriceFor(leg.id)}
                      className="text-[10.5px] font-semibold text-emerald-300 hover:text-emerald-200 bg-emerald-900/30 hover:bg-emerald-900/50 border border-emerald-700/40 rounded-md px-2 py-1.5 min-h-[34px]"
                      title={currentBook ? `Best price from ${currentBook}` : "Use best price"}
                    >
                      Use ${currentBest.toFixed(2)}
                      {currentBook && <span className="text-emerald-500/70 ml-1 text-[9.5px]">{currentBook}</span>}
                    </button>
                  ) : (
                    <span className="text-[10px] text-slate-600 leading-tight">
                      optional · enables per-leg edge call-out
                    </span>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Action row */}
        <div className="flex flex-wrap items-center gap-2 mt-3">
          <button
            onClick={addLeg}
            className="px-3 py-2 rounded-lg text-[12px] font-semibold border border-emerald-700/50 bg-emerald-900/30 text-emerald-300 hover:bg-emerald-900/50 min-h-[36px]"
          >
            + Add leg
          </button>
        </div>

        {/* Slip price — full-width on mobile, own block */}
        <div className="mt-3 pt-3 border-t border-edge/40">
          <label className="text-[10px] font-bold uppercase tracking-widest text-slate-500 block mb-1.5">
            Bookie&apos;s slip price (whole multi)
          </label>
          <div className="flex items-center gap-2">
            <input
              inputMode="decimal"
              value={slipBookPrice}
              onChange={(e) => setSlipBookPrice(e.target.value)}
              placeholder="e.g. 12.06"
              className="bg-surface-0 border border-edge rounded-md px-3 py-2 text-[14px] text-slate-100 font-mono w-32 text-center min-h-[38px]"
            />
            <p className="text-[10.5px] text-slate-500 leading-snug flex-1">
              Drop in your bookmaker&apos;s price for the whole multi to see the model&apos;s EV.
            </p>
          </div>
        </div>
      </div>

      {/* Verdict + analysis */}
      {error && (
        <div className="rounded-xl border border-amber-700/50 bg-amber-950/30 p-3 text-[12px] text-amber-300">
          {error}
        </div>
      )}

      {analysis && (
        <>
          <VerdictCard analysis={analysis} loading={loading} />
          {analysis.per_match.length > 0 && (
            <CorrelationCard analysis={analysis} />
          )}
          <PerLegEdgeCard analysis={analysis} />
          <KellyStakeCard analysis={analysis} />
          <div className="grid sm:grid-cols-2 gap-3">
            <LegImpactBar analysis={analysis} />
            <BankrollOutcome analysis={analysis} stakePctOfBank={0.01} />
          </div>
          {analysis.suggestion && (
            <SuggestionCard suggestion={analysis.suggestion} onApply={applySuggestion} />
          )}
        </>
      )}

      <p className="text-[10.5px] text-slate-600 leading-snug pt-2">
        Fair odds are a model estimate, not a guarantee. A multi loses most of the time —
        the bar above shows the model&apos;s own win chance. Stake small (quarter-Kelly
        or less). 18+ only.
      </p>
    </div>
  )
}

function VerdictCard({ analysis, loading }: { analysis: MultiAnalysis; loading: boolean }) {
  const p = analysis.combined_probability
  const odds = analysis.fair_combined_odds
  const ev = analysis.ev
  const book = analysis.slip_book_price
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
      <div className="flex items-baseline justify-between gap-3 mb-2">
        <p className="text-[11px] font-bold text-slate-300 uppercase tracking-widest">
          Model verdict {loading && <span className="text-slate-600 normal-case font-normal ml-2">updating…</span>}
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600">Combined win chance</p>
          <p className="font-mono tabular-nums text-[22px] font-bold text-emerald-400">{pctFmt(p, 1)}</p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600">Model fair odds</p>
          <p className="font-mono tabular-nums text-[22px] font-bold text-slate-100">
            {odds != null ? odds.toFixed(2) : "—"}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-wider text-slate-600">
            EV {book ? `at ${book.toFixed(2)}` : ""}
          </p>
          <p className={`font-mono tabular-nums text-[22px] font-bold ${evClass(ev)}`}>
            {ev != null ? `${ev >= 0 ? "+" : ""}${(ev * 100).toFixed(1)}%` : "—"}
          </p>
        </div>
      </div>
      {book == null && (
        <p className="text-[10.5px] text-slate-500 mt-2">
          Enter your bookmaker&apos;s combined-multi price above to see EV. Anything longer
          than <span className="text-slate-300 font-mono">{odds?.toFixed(2) ?? "—"}</span> is value
          by the model.
        </p>
      )}
    </div>
  )
}

function CorrelationCard({ analysis }: { analysis: MultiAnalysis }) {
  const hasMulti = analysis.per_match.some((pm) => pm.legs_in_match > 1)
  if (!hasMulti) return null  // nothing interesting to surface for cross-match-only slips
  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-3.5">
      <p className="text-[11px] font-bold text-slate-300 mb-0.5">Same-match correlation</p>
      <p className="text-[10.5px] text-slate-500 mb-2 leading-snug">
        Within a match the legs are NOT independent. The model reads the joint straight
        off the score grid; multiplying them naively would mis-price the slip.
      </p>
      <ul className="space-y-1.5">
        {analysis.per_match.filter((pm) => pm.legs_in_match > 1).map((pm) => {
          const corrPct = pm.correlation_effect * 100
          const sign = corrPct >= 0 ? "+" : ""
          const lead = analysis.legs.find((l) => l.match_id === pm.match_id)
          return (
            <li key={pm.match_id} className="text-[11.5px] flex items-baseline justify-between gap-2">
              <span className="text-slate-300">{lead?.match_label ?? pm.match_id}</span>
              <span className="text-slate-500 font-mono">
                joint <span className="text-emerald-400 font-bold">{(pm.joint_prob_from_grid * 100).toFixed(1)}%</span>
                {" vs naive "}
                <span className="text-slate-300">{(pm.naive_product_in_match * 100).toFixed(1)}%</span>
                <span className={`ml-2 ${corrPct >= 0 ? "text-emerald-400" : "text-amber-500"}`}>
                  ({sign}{corrPct.toFixed(1)}%)
                </span>
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function PerLegEdgeCard({ analysis }: { analysis: MultiAnalysis }) {
  return (
    <div className="rounded-xl border border-edge bg-surface-2 p-3.5">
      <p className="text-[11px] font-bold text-slate-300 mb-2">Per-leg edge</p>
      <ul className="space-y-3">
        {analysis.legs.map((leg, i) => {
          const chip = edgeChipFor(leg.edge_flag)
          const market = leg.market_implied
            ?? (leg.book_price != null ? pricePct(String(leg.book_price)) : null)
          return (
            <li key={i} className="space-y-1.5">
              <div className="flex items-center justify-between gap-2">
                <span className="text-[12px] text-slate-200 font-semibold truncate">
                  <span className="text-slate-500 font-mono mr-1">#{i + 1}</span>
                  {leg.match_label} · {leg.label}
                </span>
                <span className={`text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded-md border ${chip.cls}`}>
                  {chip.text}
                </span>
              </div>
              <EdgeBar model={leg.model_prob} market={market} />
              {leg.ev_leg != null && (
                <p className="text-[10.5px] text-slate-500">
                  Standalone EV at your price{" "}
                  <span className="text-slate-300 font-mono">
                    {leg.book_price?.toFixed(2)}
                  </span>:{" "}
                  <span className={`font-mono font-bold ${evClass(leg.ev_leg)}`}>
                    {leg.ev_leg >= 0 ? "+" : ""}{(leg.ev_leg * 100).toFixed(1)}%
                  </span>
                </p>
              )}
            </li>
          )
        })}
      </ul>
      <p className="text-[10.5px] text-slate-600 mt-2 leading-snug">
        A multi of no-edge legs just compounds the bookmaker margin. Edge-attribution
        uses the de-vigged market for 1X2 and Over/Under 2.5; other markets fall back
        to the standalone EV against your entered price.
      </p>
    </div>
  )
}

function SuggestionCard({
  suggestion, onApply,
}: { suggestion: NonNullable<MultiAnalysis["suggestion"]>; onApply: () => void }) {
  const isOptimal = suggestion.kind === "already_optimal"
  const before = suggestion.before
  const after = suggestion.after
  return (
    <div className="rounded-xl border border-emerald-700/40 bg-emerald-950/20 p-4">
      <p className="text-[11px] font-bold text-emerald-300 uppercase tracking-widest mb-1">
        {isOptimal ? "Slip is already at its best" : "A better slip"}
      </p>
      <p className="text-[12px] text-slate-300 leading-snug mb-3">{suggestion.reason}</p>
      {!isOptimal && after && (
        <div className="grid grid-cols-3 gap-3 mb-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-600">Win chance</p>
            <p className="text-[11px] text-slate-500 line-through font-mono">
              {pctFmt(before.combined_probability, 1)}
            </p>
            <p className="text-[15px] text-emerald-400 font-mono font-bold">
              {pctFmt(after.combined_probability, 1)}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-600">Fair odds</p>
            <p className="text-[11px] text-slate-500 line-through font-mono">
              {before.fair_combined_odds?.toFixed(2) ?? "—"}
            </p>
            <p className="text-[15px] text-slate-100 font-mono font-bold">
              {after.fair_combined_odds?.toFixed(2) ?? "—"}
            </p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-wider text-slate-600">
              EV {after.ev_assumes_same_vig ? "*" : ""}
            </p>
            <p className="text-[11px] text-slate-500 line-through font-mono">
              {before.ev != null ? `${(before.ev * 100).toFixed(1)}%` : "—"}
            </p>
            <p className={`text-[15px] font-mono font-bold ${evClass(after.ev)}`}>
              {after.ev != null ? `${after.ev >= 0 ? "+" : ""}${(after.ev * 100).toFixed(1)}%` : "—"}
            </p>
          </div>
        </div>
      )}
      {!isOptimal && (
        <div className="flex items-center gap-2">
          <button
            onClick={onApply}
            className="px-4 py-1.5 rounded-lg text-[12px] font-semibold border border-emerald-600 bg-emerald-700 text-white hover:bg-emerald-600"
          >
            Apply this change
          </button>
          {after?.ev_assumes_same_vig && (
            <p className="text-[10px] text-slate-500 leading-snug">
              * EV assumes your bookmaker keeps the same margin on the new slip; confirm
              the actual offered price before staking.
            </p>
          )}
        </div>
      )}
    </div>
  )
}
