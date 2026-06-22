import { TopBar } from "@/components/layout/TopBar"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "How It Works",
  description: "How the WC2026 Predictor model produces match probabilities, fair odds, and value picks for every game.",
}

const DEFINITIONS = [
  {
    term: "Strength rating (ELO)",
    body: "A number that shows how strong a team is based on their results over time. Beat a strong team and it rises. Lose to a weak one and it drops. Used across chess, esports, and football since the 1970s. Higher number means a stronger team.",
  },
  {
    term: "FIFA ranking",
    body: "The official FIFA points table. Less precise than the strength rating for match prediction but widely recognised, so we show both.",
  },
  {
    term: "Chance quality",
    body: "Measures how dangerous a team's shots actually are, not just whether they scored. A tap-in from two metres counts more than a long-range speculator. A higher number means better scoring chances, regardless of the final scoreline.",
  },
  {
    term: "EV (Expected Value)",
    body: "The mathematical edge. If we calculate a team has a 68% chance of winning but the bookmaker's odds only imply 59%, the gap is your edge. Green means we think you are getting better odds than the market is offering.",
  },
  {
    term: "Asian Handicap",
    body: "Removes the draw from the equation by giving the weaker team a virtual head start in goals. Tighter margins and lower bookmaker fees than a straight win/loss bet.",
  },
  {
    term: "Accumulator",
    body: "A single bet combining multiple matches. All legs must win for you to get paid. Higher risk, higher payout. The optimizer finds combinations where the total expected value is highest.",
  },
  {
    term: "Kelly stake",
    body: "A formula that tells you what percentage of your bankroll to bet based on your edge. We use quarter-Kelly, which is more conservative and suits tournament betting where sample size is small.",
  },
]

export default function HowItWorksPage() {
  return (
    <>
      <TopBar title="How It Works" subtitle="What the numbers mean and how predictions are made" />
      <div className="px-6 py-5 max-w-2xl">
        <p className="text-[13px] text-slate-400 mb-6 leading-relaxed">
          A statistical model generates every prediction on this site. It picks probable winners
          from team strength, recent form, and scoring patterns. These are probabilities, not
          certainties. The numbers surface the reasoning behind each pick so you can decide for yourself.
        </p>
        <div className="space-y-4">
          {DEFINITIONS.map((d) => (
            <div key={d.term} className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-5 py-4">
              <h3 className="text-[13px] font-bold text-slate-200 mb-1.5">{d.term}</h3>
              <p className="text-[12px] text-slate-400 leading-relaxed">{d.body}</p>
            </div>
          ))}
        </div>

        {/* Data sources + attributions. Required for licensed datasets. */}
        <div className="mt-8">
          <h2 className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Data sources</h2>
          <div className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-5 py-4 space-y-2.5">
            <p className="text-[12px] text-slate-400 leading-relaxed">
              <span className="text-slate-300 font-semibold">Match data, lineups, live stats:</span> api-football.
            </p>
            <p className="text-[12px] text-slate-400 leading-relaxed">
              <span className="text-slate-300 font-semibold">Historical results &amp; ratings:</span> the model is
              fit on years of international results, time-weighted toward recent and competitive matches.
            </p>
            <p className="text-[12px] text-slate-400 leading-relaxed">
              <span className="text-slate-300 font-semibold">Squad values &amp; per-90 player stats:</span> Rising Transfers
              {" "}(
              <a href="https://risingtransfers.com" target="_blank" rel="noopener noreferrer" className="text-emerald-400 hover:underline">risingtransfers.com</a>
              ), used under{" "}
              <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer" className="text-emerald-400 hover:underline">CC BY 4.0</a>.
              An AI transfer-value estimate per player (summed per nation) feeds a small squad-quality
              adjustment, and 2025-26 club-season per-90 numbers appear on the team and player pages.
            </p>
            <p className="text-[12px] text-slate-400 leading-relaxed">
              <span className="text-slate-300 font-semibold">Sharp odds anchor:</span> Pinnacle (via SportsGameOdds),
              used to measure value against the sharpest available line rather than soft bookmaker prices.
            </p>
          </div>
        </div>
      </div>
    </>
  )
}
