import Link from "next/link"
import { ArrowRight, GitFork } from "lucide-react"
import type { TournamentProjection, HistoryStats, TournamentTeam } from "@/lib/types"

function pct(v: number) {
  if (v >= 0.995) return "99"
  if (v > 0 && v < 0.005) return "<1"
  return String(Math.round(v * 100))
}

function ContenderCard({ t, value, rank, label }: { t: TournamentTeam; value: number; rank: number; label: string }) {
  const leader = rank === 1
  return (
    <Link
      href={`/team/${t.code}?from=%2F`}
      className={[
        "group relative overflow-hidden rounded-2xl border p-4 transition-all duration-150 hover:-translate-y-0.5",
        leader
          ? "border-amber-400/30 bg-gradient-to-b from-amber-400/[0.12] to-surface-2 shadow-glow-gold"
          : "border-edge bg-gradient-to-b from-surface-3 to-surface-2 shadow-e1 hover:border-edge-strong",
      ].join(" ")}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className={`font-mono text-[12px] tabular-nums ${leader ? "text-amber-400" : "text-slate-500"}`}>
          {leader ? "★ 1" : rank}
        </span>
        {t.flag_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={t.flag_url} alt="" className="w-9 h-[26px] rounded object-cover ring-1 ring-white/15 shadow" />
        ) : (
          <span className="w-9 h-[26px] rounded ring-1 ring-white/15" style={{ background: t.primary_color || "#1e293b" }} />
        )}
        <span className={`text-[15px] font-bold truncate ${leader ? "text-amber-50" : "text-slate-100"}`}>{t.name}</span>
      </div>
      <div className="flex items-end gap-1.5">
        <span className={`font-display font-bold tabular-nums leading-none text-[44px] sm:text-[52px] ${leader ? "text-amber-300" : "text-ink"}`}>
          {pct(value)}
        </span>
        <span className={`text-[18px] font-bold mb-1 ${leader ? "text-amber-300/70" : "text-slate-500"}`}>%</span>
      </div>
      <p className="text-[11px] text-slate-500 mt-1">{label}</p>
    </Link>
  )
}

export function HomeHero({ proj, stats }: { proj: TournamentProjection | null; stats: HistoryStats | null }) {
  const hasTitle = !!proj?.has_knockout && proj.teams.some((t) => t.p_title != null)
  const top = proj?.teams ?? []
  const metric = (t: TournamentTeam) => (hasTitle ? (t.p_title ?? 0) : t.p_advance)
  const sorted = [...top].sort((a, b) => metric(b) - metric(a)).slice(0, 3)
  const label = hasTitle ? "to win the World Cup" : "to reach the knockouts"

  const liveTracked = stats && stats.total > 0
  const hitRate = liveTracked ? `${Math.round((stats!.accuracy ?? 0) * 100)}% pick hit rate` : "Validated on 1,500+ internationals"

  return (
    <section className="relative overflow-hidden rounded-3xl border border-edge shadow-e2 isolate">
      {/* atmosphere: pitch-lit gradient + faint mowed-grass stripes + emerald glow + watermark */}
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(125%_120%_at_50%_-15%,#103a2c_0%,#0a1a18_42%,#07090e_100%)]" />
      <div
        className="absolute inset-0 -z-10 opacity-[0.05]"
        style={{ backgroundImage: "repeating-linear-gradient(102deg, transparent 0 64px, rgba(255,255,255,0.6) 64px 65px)" }}
      />
      <div className="absolute -top-28 left-1/3 w-[560px] h-[300px] rounded-full bg-emerald-500/20 blur-[110px] -z-10 pointer-events-none" />
      <div className="absolute -right-6 -bottom-12 font-display font-bold text-[180px] sm:text-[240px] leading-none text-white/[0.025] select-none -z-10 pointer-events-none">
        26
      </div>

      <div className="px-5 sm:px-9 py-9 sm:py-12">
        <p className="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-400/80">
          FIFA World Cup 2026 · live model projections
        </p>
        <h1 className="font-display font-bold tracking-[-0.03em] text-ink leading-[0.98] mt-3 text-[40px] sm:text-[58px] max-w-2xl text-balance">
          {hasTitle ? "Who lifts the trophy?" : "Who reaches the knockouts?"}
        </h1>
        <p className="text-[14px] sm:text-[15px] text-slate-400 mt-4 max-w-xl leading-relaxed">
          20,000 simulations of every remaining match, from a model that grades its own
          accuracy in public. The favourites right now:
        </p>

        {sorted.length > 0 && (
          <div className="mt-6 grid grid-cols-1 sm:grid-cols-3 gap-3 max-w-3xl">
            {sorted.map((t, i) => (
              <ContenderCard key={t.code} t={t} value={metric(t)} rank={i + 1} label={label} />
            ))}
          </div>
        )}

        <div className="mt-7 flex flex-wrap items-center gap-3">
          <Link
            href="/winner"
            className="inline-flex items-center gap-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-[#06120c] font-semibold text-[14px] px-5 py-2.5 transition-colors"
          >
            See full projections <ArrowRight size={16} />
          </Link>
          {hasTitle && (
            <Link
              href="/bracket"
              className="inline-flex items-center gap-2 rounded-xl border border-edge hover:border-emerald-500/40 bg-surface-2/60 text-slate-200 font-semibold text-[13px] px-4 py-2.5 transition-colors"
            >
              <GitFork size={15} className="text-emerald-400" /> Projected bracket
            </Link>
          )}
          <Link
            href="/performance"
            className="inline-flex items-center gap-2 rounded-xl border border-edge hover:border-emerald-500/40 bg-surface-2/60 text-slate-300 font-semibold text-[13px] px-4 py-2.5 transition-colors"
          >
            <span className="font-mono tabular-nums text-emerald-400">{hitRate}</span>
            <span className="text-slate-500">· graded in public</span>
            <ArrowRight size={14} className="text-slate-500" />
          </Link>
        </div>
      </div>
    </section>
  )
}
