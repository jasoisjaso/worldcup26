import type { Metadata } from "next"
import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import { resolveBack } from "@/lib/back-nav"

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  try {
    const d = await api.playerProfile(Number(params.id))
    return {
      title: `${d.player.name}: stats and profile`,
      description: `${d.player.name} season stats, goals, assists, minutes, recent matches.${d.player.team_name ? ` Plays for ${d.player.team_name}.` : ""}`,
    }
  } catch {
    return { title: "Player" }
  }
}

function StatTile({ value, label, color }: { value: number | string; label: string; color: string }) {
  return (
    <div className="text-center">
      <p className={`font-mono text-[22px] sm:text-[26px] font-black tabular-nums leading-none ${color}`}>{value}</p>
      <p className="text-[10px] text-slate-500 uppercase tracking-wider mt-1">{label}</p>
    </div>
  )
}

export default async function PlayerPage({ params, searchParams }: { params: { id: string }; searchParams: { from?: string } }) {
  let data: Awaited<ReturnType<typeof api.playerProfile>> | null = null
  try {
    data = await api.playerProfile(Number(params.id))
  } catch {
    /* 404 below */
  }
  const back = resolveBack(searchParams.from, { href: "/", label: "Home" })

  if (!data) {
    return (
      <>
        <TopBar title="Player" backHref={back.href} backLabel={back.label} />
        <p className="text-slate-500 text-sm py-16 text-center px-4">Player not found.</p>
      </>
    )
  }
  const p = data.player
  const t = data.totals

  return (
    <>
      <TopBar
        title={p.name}
        subtitle={p.team_name || p.nation_name || ""}
        backHref={back.href}
        backLabel={back.label}
      />
      <div className="max-w-2xl mx-auto px-3 sm:px-5 py-5">
        {/* Hero */}
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-5 mb-5 flex items-center gap-4">
          {p.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.photo_url} alt={p.name} className="w-20 h-20 rounded-full object-cover ring-2 ring-emerald-500/20 bg-slate-800 shrink-0" />
          ) : (
            <div className="w-20 h-20 rounded-full bg-slate-800 ring-2 ring-emerald-500/20 shrink-0 flex items-center justify-center text-slate-400 font-bold text-[20px]">
              {p.name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase()}
            </div>
          )}
          <div className="min-w-0 flex-1">
            <h1 className="text-[22px] font-black text-white leading-tight">{p.name}</h1>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {p.position}{p.age ? ` · ${p.age} yrs` : ""}{p.nationality ? ` · ${p.nationality}` : ""}
            </p>
            {(p.height || p.weight) && (
              <p className="text-[11px] text-slate-600 mt-0.5">{[p.height, p.weight].filter(Boolean).join(" · ")}</p>
            )}
            {p.nation_code && p.nation_name && (
              <Link
                href={`/team/${p.nation_code}?from=${encodeURIComponent(`/player/${p.id}`)}`}
                className="inline-flex items-center gap-1.5 mt-2 text-[11px] text-emerald-400 hover:text-emerald-300"
              >
                {p.nation_flag && (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={p.nation_flag} alt="" className="w-4 h-3 rounded-[1px] object-cover" />
                )}
                {p.nation_name} squad →
              </Link>
            )}
          </div>
        </div>

        {/* Career totals */}
        {t.appearances > 0 ? (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/80 mb-3">Career totals</p>
            <div className="grid grid-cols-4 gap-2">
              <StatTile value={t.appearances} label="Apps" color="text-white" />
              <StatTile value={t.goals} label="Goals" color="text-amber-400" />
              <StatTile value={t.assists} label="Assists" color="text-emerald-400" />
              <StatTile value={Math.round(t.minutes / 90)} label="90s" color="text-slate-300" />
            </div>
            {(t.yellow_cards > 0 || t.red_cards > 0) && (
              <div className="mt-4 pt-4 border-t border-edge/40 flex items-center gap-4 text-[11px] text-slate-500">
                {t.yellow_cards > 0 && (
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2.5 rounded-sm bg-amber-400" aria-hidden /> {t.yellow_cards} yellow
                  </span>
                )}
                {t.red_cards > 0 && (
                  <span className="flex items-center gap-1.5">
                    <span className="w-2 h-2.5 rounded-sm bg-rose-500" aria-hidden /> {t.red_cards} red
                  </span>
                )}
              </div>
            )}
            {data.career_stats.length > 1 && (
              <p className="text-[10px] text-slate-600 mt-3">Totals across {data.career_stats.length} club records.</p>
            )}
          </div>
        ) : (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Career totals</p>
            <p className="text-[12px] text-slate-600">
              Season stats not collected yet for this player. Stats appear after our archive harvests their club season.
            </p>
          </div>
        )}

        {/* Per-team breakdown */}
        {data.career_stats.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">By team</p>
            <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 overflow-hidden divide-y divide-edge/30">
              {data.career_stats.map((s, i) => (
                <div key={i} className="flex items-center gap-3 px-4 py-2.5">
                  <span className="text-[13px] text-slate-200 flex-1 truncate">{s.team_name || "Unknown"}</span>
                  <span className="text-[11px] text-slate-600 font-mono tabular-nums shrink-0">{s.appearances} apps</span>
                  <span className="text-[11px] text-amber-400 font-mono tabular-nums shrink-0 w-8 text-right">{s.goals}g</span>
                  <span className="text-[11px] text-emerald-400 font-mono tabular-nums shrink-0 w-8 text-right">{s.assists}a</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Recent matches — populated by /fixtures/players harvest, may be empty for now */}
        {data.recent_matches.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Recent matches</p>
            <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 overflow-hidden divide-y divide-edge/30">
              {data.recent_matches.map((m) => (
                <div key={m.api_fixture_id} className="flex items-center gap-3 px-4 py-2.5 text-[12px]">
                  <span className="text-slate-500 font-mono tabular-nums w-12 shrink-0">{m.minutes}&apos;</span>
                  <span className="flex-1 truncate">
                    {m.goals > 0 && <span className="text-amber-400 font-bold">{m.goals}G </span>}
                    {m.assists > 0 && <span className="text-emerald-400 font-bold">{m.assists}A </span>}
                    {!m.goals && !m.assists && <span className="text-slate-600">No goal involvement</span>}
                  </span>
                  {m.rating && <span className="font-mono tabular-nums text-slate-400 text-[11px] shrink-0">{m.rating.toFixed(1)}</span>}
                  {m.match_id && (
                    <Link href={`/match/${m.match_id}?from=${encodeURIComponent(`/player/${p.id}`)}`} className="text-emerald-400 text-[11px] hover:underline shrink-0">View</Link>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
