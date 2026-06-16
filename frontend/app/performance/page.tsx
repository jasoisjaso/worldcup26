import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { ReliabilityCurve } from "@/components/performance/ReliabilityCurve"
import { ProfitCurve } from "@/components/performance/ProfitCurve"
import { ClvScatter } from "@/components/performance/ClvScatter"
import { api } from "@/lib/api"
import type { Calibration, HistoryStats, MarketCalibration, HistoryEntry } from "@/lib/types"

export const metadata: Metadata = {
  title: "Model Report Card: How Accurate Are the Predictions?",
  description:
    "Every WC2026 prediction is scored after kickoff with proper scoring rules (RPS, Brier, log-loss and calibration) and published here. See how the model is doing and how it improves.",
  alternates: { canonical: "https://wc26.tinjak.com/performance" },
}

// Always render fresh; never prerender an empty build-time snapshot.
export const dynamic = "force-dynamic"

function fmt(n: number | undefined | null, dp = 3): string {
  return n == null ? "-" : n.toFixed(dp)
}

function Grade({
  label, value, hint, tone = "neutral",
}: { label: string; value: string; hint: string; tone?: "good" | "ok" | "bad" | "neutral" }) {
  const dot = { good: "bg-emerald-400", ok: "bg-amber-400", bad: "bg-rose-400", neutral: "bg-slate-600" }[tone]
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
      <div className="flex items-center gap-1.5 mb-1.5">
        <span className={`w-1.5 h-1.5 rounded-full ${dot}`} />
        <p className="text-[10px] font-bold uppercase tracking-[0.15em] text-slate-500">{label}</p>
      </div>
      <p className="font-mono text-[26px] tabular-nums font-bold text-white leading-none">{value}</p>
      <p className="text-[11px] text-slate-500 mt-2 leading-snug">{hint}</p>
    </div>
  )
}

function rpsTone(v?: number) {
  if (v == null) return "neutral" as const
  if (v <= 0.18) return "good" as const
  if (v <= 0.21) return "ok" as const
  return "bad" as const
}
function eceTone(v?: number) {
  if (v == null) return "neutral" as const
  if (v <= 0.05) return "good" as const
  if (v <= 0.1) return "ok" as const
  return "bad" as const
}

function MarketCard({ name, c }: { name: string; c: MarketCalibration | null | undefined }) {
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-3.5">
      <div className="flex items-baseline justify-between mb-2">
        <p className="text-[12px] font-bold text-slate-200">{name}</p>
        <p className="text-[10px] text-slate-600 font-mono">{c ? `${c.n} settled` : "no data"}</p>
      </div>
      {c ? (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Brier</p>
            <p className="font-mono text-[15px] tabular-nums text-slate-100">{fmt(c.brier)}</p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Calib. error</p>
            <p className="font-mono text-[15px] tabular-nums text-slate-100">{fmt(c.ece)}</p>
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-slate-600">Scored once these markets settle.</p>
      )}
    </div>
  )
}

function ClvBlock({ stats }: { stats: HistoryStats }) {
  const hasClv = stats.clv_n != null && stats.clv_n > 0
  return (
    <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
      <p className="text-[12px] font-bold text-slate-200 mb-1">Beating the market (CLV)</p>
      <p className="text-[11px] text-slate-500 leading-snug mb-3">
        Closing Line Value compares the price we logged against the sharp closing line. It is the earliest
        reliable proof of a real edge, long before win-rate can tell.
      </p>
      {hasClv ? (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Avg CLV</p>
            <p className={`font-mono text-[20px] tabular-nums font-bold ${(stats.avg_clv ?? 0) > 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {(stats.avg_clv ?? 0) > 0 ? "+" : ""}{((stats.avg_clv ?? 0) * 100).toFixed(1)}%
            </p>
          </div>
          <div>
            <p className="text-[9px] uppercase tracking-wider text-slate-600">Beat the close</p>
            <p className="font-mono text-[20px] tabular-nums font-bold text-slate-100">
              {Math.round((stats.clv_beat_close_rate ?? 0) * 100)}%
            </p>
            <p className="text-[9px] text-slate-600">{stats.clv_n} pick{stats.clv_n === 1 ? "" : "s"}</p>
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-slate-600">Captured automatically as picks approach kickoff.</p>
      )}
    </div>
  )
}

export default async function PerformancePage() {
  let cal: Calibration | null = null
  let stats: HistoryStats | null = null
  let entries: HistoryEntry[] = []
  try {
    ;[cal, stats, entries] = await Promise.all([
      api.calibration(),
      api.historyStats(),
      api.history().catch(() => []),
    ])
  } catch {
    /* render empty state */
  }
  const settledCount = entries.filter((e) => e.correct != null).length

  const live = cal && cal.n > 0
  const m = cal?.by_market
  const versions = cal?.by_model_version
    ? Object.entries(cal.by_model_version).sort((a, b) => a[1].rps - b[1].rps)
    : []

  return (
    <>
      <TopBar title="Model Report Card" subtitle="How the model is doing, and improving" />

      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">
        {/* hero */}
        <div className="mb-6">
          <p className="text-[11px] font-bold uppercase tracking-[0.2em] text-emerald-400/80">Graded in public</p>
          <h1 className="text-[26px] sm:text-[32px] font-black tracking-tight text-white leading-[1.08] mt-1">
            Every prediction, scored after the whistle.
          </h1>
          <p className="text-[13px] text-slate-400 mt-2 max-w-xl">
            Before each kickoff the model's full probability distribution is locked in. After the result we
            score it with the same proper scoring rules a forecasting researcher would use. No cherry-picking,
            no hindsight. This is the honest record.
          </p>
        </div>

        {/* live grades */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">
          {live ? `Live · ${cal!.n} match${cal!.n === 1 ? "" : "es"} scored` : "Live tracking"}
        </p>
        {live ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 mb-6">
            <Grade label="RPS" value={fmt(cal!.rps)} tone={rpsTone(cal!.rps)} hint="Ranked probability score. Lower is sharper; under 0.18 is strong." />
            <Grade label="Log loss" value={fmt(cal!.log_loss)} hint="Punishes confident wrong calls hardest. Lower is better." />
            <Grade label="Brier" value={fmt(cal!.brier)} hint="Mean squared error of the probabilities. Lower is better." />
            <Grade label="Calib. error" value={fmt(cal!.ece_winner, 3)} tone={eceTone(cal!.ece_winner)} hint="How far stated odds drift from reality. Under 0.05 is well-calibrated." />
          </div>
        ) : null}
        {live && cal!.n < 40 && (
          <p className="text-[11px] text-amber-400/80 -mt-3 mb-6">
            Early sample ({cal!.n} matches). These swing hard match to match and settle toward the backtest
            (RPS around 0.17) as more games are played. Read them as a running scoreboard, not a verdict yet.
          </p>
        )}
        {!live && (
          <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4 mb-6">
            <p className="text-[13px] text-slate-300 font-semibold mb-1">Tracking starts at the first kickoff.</p>
            <p className="text-[12px] text-slate-500 leading-relaxed">
              The live scoreboard fills in as group games are played. In <span className="text-slate-300">pre-tournament
              walk-forward validation</span> over ~1,500 out-of-sample internationals the goal model scores
              <span className="font-mono text-slate-200"> RPS ≈ 0.170</span> and a calibration error of
              <span className="font-mono text-slate-200"> ≈ 0.03</span>, beating both an Elo and a climatology
              baseline. Those are the bars to hold once real matches land here.
            </p>
          </div>
        )}

        {/* reliability + by-market */}
        <div className="grid md:grid-cols-2 gap-4 mb-6">
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
            <p className="text-[12px] font-bold text-slate-200 mb-1">Calibration curve</p>
            <p className="text-[11px] text-slate-500 mb-2 leading-snug">
              On the dashed line, a stated 70% happens 70% of the time.
            </p>
            {live && cal!.reliability_winner && cal!.reliability_winner.length > 0 ? (
              <ReliabilityCurve bins={cal!.reliability_winner} />
            ) : (
              <div className="h-[180px] flex items-center justify-center text-[12px] text-slate-600 text-center px-4">
                The curve draws itself as matches are scored.
              </div>
            )}
          </div>

          <div className="space-y-2.5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500">By market</p>
            <MarketCard name="Match result (1X2)" c={m?.result_1x2} />
            <MarketCard name="Over / Under 2.5" c={m?.over_under_2_5} />
            <MarketCard name="Both teams to score" c={m?.btts} />
          </div>
        </div>

        {/* proof: profit curve + CLV scatter */}
        {settledCount > 0 && (
          <>
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Betting proof</p>
            <div className="grid md:grid-cols-2 gap-4 mb-6">
              <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
                <p className="text-[12px] font-bold text-slate-200 mb-2">Profit at flat stakes</p>
                <ProfitCurve entries={entries} />
              </div>
              <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
                <p className="text-[12px] font-bold text-slate-200 mb-2">Closing line value</p>
                <ClvScatter entries={entries} />
              </div>
            </div>
          </>
        )}

        {/* how it improves: version ladder */}
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-6">
          <p className="text-[12px] font-bold text-slate-200 mb-1">How it improves</p>
          <p className="text-[11px] text-slate-500 leading-snug mb-3">
            Every prediction is stamped with the model version that made it, so each change has to earn its keep.
            Lower RPS = a sharper model.
          </p>
          {versions.length > 0 ? (
            <div className="space-y-1.5">
              {versions.map(([v, s], i) => (
                <div key={v} className="flex items-center gap-3">
                  <span className="font-mono text-[12px] text-slate-300 w-12">v{v}</span>
                  <div className="flex-1 h-2 rounded-full bg-white/[0.04] overflow-hidden">
                    <div
                      className={`h-full rounded-full ${i === 0 ? "bg-emerald-400" : "bg-slate-600"}`}
                      style={{ width: `${Math.min(100, (s.rps / 0.3) * 100)}%` }}
                    />
                  </div>
                  <span className="font-mono text-[12px] tabular-nums text-slate-200 w-14 text-right">{fmt(s.rps)}</span>
                  <span className="font-mono text-[10px] text-slate-600 w-12 text-right">n={s.n}</span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-[11px] text-slate-600">Version-by-version scores appear once matches are played.</p>
          )}
        </div>

        {/* picks track record + CLV */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Value picks track record</p>
        <div className="grid sm:grid-cols-2 gap-4">
          <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-4">
            {stats && stats.total > 0 ? (
              <div className="grid grid-cols-3 gap-3">
                <div>
                  <p className="text-[9px] uppercase tracking-wider text-slate-600">Hit rate</p>
                  <p className="font-mono text-[20px] tabular-nums font-bold text-white">{Math.round((stats.accuracy ?? 0) * 100)}%</p>
                  <p className="text-[9px] text-slate-600">{stats.correct}/{stats.total}</p>
                </div>
                <div>
                  <p className="text-[9px] uppercase tracking-wider text-slate-600">ROI</p>
                  <p className={`font-mono text-[20px] tabular-nums font-bold ${(stats.roi ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                    {(stats.roi ?? 0) >= 0 ? "+" : ""}{((stats.roi ?? 0) * 100).toFixed(1)}%
                  </p>
                </div>
                <div>
                  <p className="text-[9px] uppercase tracking-wider text-slate-600">Avg edge</p>
                  <p className="font-mono text-[20px] tabular-nums font-bold text-slate-100">{((stats.avg_ev ?? 0) * 100).toFixed(1)}%</p>
                </div>
              </div>
            ) : (
              <p className="text-[12px] text-slate-500">
                Picks are logged automatically when the model finds value before kickoff. The settled record shows here.
              </p>
            )}
          </div>
          {stats && <ClvBlock stats={stats} />}
        </div>

        <p className="text-[11px] text-slate-500 mt-5 leading-relaxed">
          The headline scores use every snapshotted match, not just the value picks, so the calibration is
          unbiased by which bets we chose. Read the full method on{" "}
          <a href="/how-it-works" className="text-emerald-400 hover:underline">How it works</a>.
        </p>
      </div>
    </>
  )
}
