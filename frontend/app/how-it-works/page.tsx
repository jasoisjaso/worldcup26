import { TopBar } from "@/components/layout/TopBar"

import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "How It Works",
  description: "How the WC2026 Predictor model produces match probabilities, fair odds, and value picks for every game — the engine, the calibration, and the honesty checks.",
}

// How the engine actually works, in plain language but reflecting the REAL
// pipeline (DC+ELO blend, calibration shrinkage, market blend, pick grading).
const PIPELINE = [
  {
    step: "1. Team strength",
    body: "Each team gets a strength rating from a Dixon-Coles model fit on years of international results — more weight on recent and competitive matches, World Cup games weighted heaviest. That's blended with an Elo rating, which leans in harder when two teams come from different confederations (where the historical-goals model is least reliable).",
  },
  {
    step: "2. Match context",
    body: "On top of strength, a capped stack of context adjustments nudges each team's expected goals: rest days, travel, altitude, confirmed lineups, injuries, head-to-head history, recent harvested xG, set-piece threat and squad market value. The whole stack is clamped so correlated factors can't compound into an extreme number.",
  },
  {
    step: "3. Score distribution",
    body: "Those expected-goals numbers feed a Dixon-Coles score matrix — the probability of every scoreline. Aggregating it gives win/draw/loss, over/under, both-teams-to-score, Asian handicap, correct score and ~30 markets in all, internally consistent because they come from one matrix.",
  },
  {
    step: "4. Calibration",
    body: "Raw Poisson-style models are known to under-rate draws and be over-confident in the middle of the range. We apply a small, capped calibration step that lifts the draw toward the real international base rate for even matches and gently softens over-confident favourites. It can only narrow that known bias, never invent a new opinion.",
  },
  {
    step: "5. Market blend",
    body: "The calibrated model is blended 70/30 with the de-vigged bookmaker line (using Shin's method, which corrects the favourite-longshot bias of naive de-vigging). When a sharp Pinnacle line is available it's used as the anchor instead of soft books. The blend is what you see; the raw model opinion is kept separately to measure genuine edge.",
  },
  {
    step: "6. Value + pick grading",
    body: "Edge is measured as the raw model probability vs the de-vigged line — so the value finder hunts real disagreement, not agreement with the market. Every candidate is graded: Core (a believable, sample-backed edge under a sanity cap — counts toward the public record) or Speculative (the model sees something we can't fully stand behind — shown for your discretion, kept out of the graded record). Implausibly large edges are rejected outright as model error.",
  },
  {
    step: "7. Honesty checks",
    body: "Every pre-kickoff probability is locked in and scored after the result with proper scoring rules (Brier, log-loss, calibration). We also track Closing Line Value — whether our price beat the sharp closing line — the earliest reliable proof an edge is real. The full record is public on the Report Card, including where the model has been over-confident.",
  },
]

const DEFINITIONS = [
  {
    term: "Strength rating (Elo + Dixon-Coles)",
    body: "How strong a team is from its results over time. We combine a classic Elo rating with a Dixon-Coles goals model and lean on Elo more for cross-confederation matchups, where the goals model is least tested. Higher means stronger.",
  },
  {
    term: "Expected goals (xG)",
    body: "How dangerous a team's shots actually are, not just whether they scored. A tap-in counts more than a long-range hopeful effort. We use harvested match xG as a recent-form signal once a team has enough archived games.",
  },
  {
    term: "Calibration",
    body: "Whether stated odds match reality: when the model says 60%, does it happen ~60% of the time? The Report Card shows this per confidence band — including where the model has run hot or cold.",
  },
  {
    term: "EV (Expected Value)",
    body: "The mathematical edge. If the model says a team wins 68% but the odds only imply 59%, the gap is your edge. We measure it against the sharpest available line and cap implausible edges as likely model error.",
  },
  {
    term: "Core vs Speculative picks",
    body: "Core picks are believable, sample-backed edges that count toward the public record. Speculative picks are ones the model flags but we can't fully stand behind — shown at your discretion and deliberately excluded from the graded hit-rate and ROI.",
  },
  {
    term: "Model confidence",
    body: "On each match we compare our two internal views — the Elo view and the Dixon-Coles view. When they disagree strongly we say so (\"lower confidence\"), so you can weight an uncertain call accordingly.",
  },
  {
    term: "CLV (Closing Line Value)",
    body: "Did the price we flagged beat the sharp closing line? Over many picks, beating the close is the earliest reliable sign an edge is real — long before win-rate or profit can prove it.",
  },
  {
    term: "Asian Handicap",
    body: "Removes the draw by giving the weaker team a virtual head start in goals. Tighter margins and lower bookmaker fees than a straight win/loss bet.",
  },
  {
    term: "Kelly stake",
    body: "What fraction of a bankroll to bet given the edge. We use quarter-Kelly — conservative, which suits tournament betting where the sample is small.",
  },
]

export default function HowItWorksPage() {
  return (
    <>
      <TopBar title="How It Works" subtitle="The engine, the calibration, and the honesty checks" />
      <div className="px-6 py-5 max-w-2xl">
        <p className="text-[13px] text-slate-400 mb-6 leading-relaxed">
          Every prediction here comes from a statistical model — not opinion. Below is exactly how a
          number is built, from team strength through to the value picks, and the honesty checks that
          keep us accountable. These are probabilities, not certainties; the point is to show the
          reasoning so you can decide for yourself.
        </p>

        {/* The pipeline — how the engine actually works, in order. */}
        <h2 className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">How a prediction is built</h2>
        <ol className="space-y-3 mb-8">
          {PIPELINE.map((p) => (
            <li key={p.step} className="bg-surface-2 border border-edge rounded-xl shadow-e1 px-5 py-4">
              <h3 className="text-[13px] font-bold text-emerald-300/90 mb-1.5">{p.step}</h3>
              <p className="text-[12px] text-slate-400 leading-relaxed">{p.body}</p>
            </li>
          ))}
        </ol>

        {/* Glossary */}
        <h2 className="text-[11px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">The terms</h2>
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
            <p className="text-[12px] text-slate-400 leading-relaxed">
              <span className="text-slate-300 font-semibold">Benchmark:</span> the Opta supercomputer&apos;s
              pre-tournament forecast, for an independent comparison on the Report Card.
            </p>
          </div>
        </div>

        <p className="text-[11px] text-slate-500 mt-5 leading-relaxed">
          Model estimates, not guarantees. A strong edge can still lose. For 18+ only. Bet only what you
          can afford to lose, and take a break if it stops being fun.
        </p>
      </div>
    </>
  )
}
