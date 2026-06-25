import path from "node:path"
import fs from "node:fs/promises"
import { TrendingUp, TrendingDown, Eye } from "lucide-react"

// StockTwits-style divergence read: when the model strongly favours a side but
// community sentiment about them is panic (or the opposite), that gap is the
// signal. When model and community agree, we say so briefly and move on. When
// either side has no signal, the panel hides.

type Sentiment = "panic" | "praise" | "mixed" | null

type Entry = {
  sentiment?: Sentiment
}

type Snapshot = {
  teams: Record<string, Entry>
}

type Props = {
  homeCode: string
  awayCode: string
  homeName: string
  awayName: string
  homeWin: number   // 0..1
  awayWin: number   // 0..1
  drawProb: number  // 0..1
}

async function loadSentiment(code: string): Promise<Sentiment> {
  try {
    const p = path.join(process.cwd(), "public", "data", "team-news.json")
    const snap = JSON.parse(await fs.readFile(p, "utf-8")) as Snapshot
    return snap.teams?.[code]?.sentiment ?? null
  } catch {
    return null
  }
}

type Divergence = {
  side: "home" | "away"
  teamName: string
  kind: "fade_panic" | "back_panic" | "fade_praise" | "back_praise"
  modelProb: number
  sentiment: NonNullable<Sentiment>
  headline: string
  detail: string
}

function classify(
  side: "home" | "away",
  teamName: string,
  prob: number,           // 0..1
  sentiment: Sentiment,
): Divergence | null {
  if (!sentiment || sentiment === "mixed") return null
  const pct = Math.round(prob * 100)
  // Model says favourite (>55%) but community panic about them. Fade the panic.
  if (sentiment === "panic" && prob > 0.55) {
    return {
      side, teamName, sentiment, modelProb: prob,
      kind: "fade_panic",
      headline: `Fade the ${teamName} panic`,
      detail: `Model still has ${teamName} at ${pct}% to win — community chatter is in panic mode. Disagreement is where value sits.`,
    }
  }
  // Model says big underdog (<30%) but community praising them. Crowd sees something model doesn't.
  if (sentiment === "praise" && prob < 0.30) {
    return {
      side, teamName, sentiment, modelProb: prob,
      kind: "back_praise",
      headline: `Crowd backing ${teamName}, model isn't`,
      detail: `Model has ${teamName} at just ${pct}% to win, but community sentiment is positive. Could be roster / form info the rating model hasn't caught up to.`,
    }
  }
  // Model says big favourite (>55%) and community agrees — minor signal, low priority
  if (sentiment === "praise" && prob > 0.55) {
    return {
      side, teamName, sentiment, modelProb: prob,
      kind: "back_praise",
      headline: `${teamName}: model + crowd aligned`,
      detail: `Model: ${pct}% to win. Community: praising. Consensus pick — less edge but lower risk.`,
    }
  }
  // Model says underdog and community panicking — also consensus, no value here
  if (sentiment === "panic" && prob < 0.30) {
    return {
      side, teamName, sentiment, modelProb: prob,
      kind: "fade_panic",
      headline: `${teamName}: model + crowd both bearish`,
      detail: `Model: ${pct}% to win. Community: panicking. Consensus fade — less edge but lower risk.`,
    }
  }
  return null
}

// Rank divergences by interestingness — "fade panic on a favourite" and
// "back praise on an underdog" are the StockTwits-style edges. Consensus
// reads come last.
const PRIORITY: Record<Divergence["kind"], number> = {
  fade_panic: 0,
  back_praise: 1,
  fade_praise: 2,
  back_panic: 3,
}

function isContrarian(d: Divergence): boolean {
  return d.kind === "fade_panic" || (d.kind === "back_praise" && d.modelProb < 0.5)
}

const ICON_FOR: Record<Divergence["kind"], typeof TrendingUp> = {
  fade_panic:  TrendingUp,
  back_praise: TrendingUp,
  fade_praise: TrendingDown,
  back_panic:  Eye,
}

const ACCENT_CLS: Record<Divergence["kind"], string> = {
  fade_panic:  "border-cyan-500/40 bg-cyan-500/5",
  back_praise: "border-cyan-500/40 bg-cyan-500/5",
  fade_praise: "border-slate-700 bg-surface-2",
  back_panic:  "border-slate-700 bg-surface-2",
}

export async function CommunityVsModel({
  homeCode, awayCode, homeName, awayName, homeWin, awayWin,
}: Props) {
  const [homeSentiment, awaySentiment] = await Promise.all([
    loadSentiment(homeCode),
    loadSentiment(awayCode),
  ])

  const divs: Divergence[] = []
  const dHome = classify("home", homeName, homeWin, homeSentiment)
  const dAway = classify("away", awayName, awayWin, awaySentiment)
  if (dHome) divs.push(dHome)
  if (dAway) divs.push(dAway)

  if (divs.length === 0) return null

  divs.sort((a, b) => PRIORITY[a.kind] - PRIORITY[b.kind])
  const top = divs[0]
  const Icon = ICON_FOR[top.kind]
  const contrarian = isContrarian(top)

  return (
    <section className={`rounded-2xl border p-4 mb-5 ${ACCENT_CLS[top.kind]}`}>
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">
          Community vs model
        </p>
        {contrarian && (
          <span className="text-[10px] font-bold uppercase tracking-wider text-cyan-300">
            Edge
          </span>
        )}
      </div>

      <div className="flex items-start gap-3">
        <Icon className={`w-5 h-5 mt-0.5 shrink-0 ${contrarian ? "text-cyan-300" : "text-slate-400"}`} />
        <div className="min-w-0">
          <p className="text-[14px] font-semibold text-slate-100 leading-snug">
            {top.headline}
          </p>
          <p className="text-[12.5px] text-slate-400 leading-snug mt-1">
            {top.detail}
          </p>
        </div>
      </div>

      {divs.length > 1 && (
        <p className="text-[11px] text-slate-500 mt-3 pt-3 border-t border-slate-800">
          Also: {divs[1].headline}.
        </p>
      )}
    </section>
  )
}
