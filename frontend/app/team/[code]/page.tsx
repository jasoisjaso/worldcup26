import type { Metadata } from "next"
import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { TopBar } from "@/components/layout/TopBar"
import { KickoffTime } from "@/components/common/KickoffTime"
import { api } from "@/lib/api"
import { resolveBack } from "@/lib/back-nav"
import { TeamRadar } from "@/components/viz/TeamRadar"
import { SurvivalFunnel } from "@/components/viz/SurvivalFunnel"
import { PlayerCard } from "@/components/team/PlayerCard"
import { FormStrip } from "@/components/team/FormStrip"
import type { TeamProfile, TournamentTeam, GroupStanding, RadarData } from "@/lib/types"

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: { params: { code: string } }): Promise<Metadata> {
  try {
    const t = await api.teamProfile(params.code)
    return {
      title: `${t.name}: World Cup 2026 Prediction & Odds`,
      description: `${t.name}'s 2026 World Cup outlook: chance to win the group, reach the knockouts and win the trophy, plus every fixture with model odds and full squad with season stats.`,
      alternates: { canonical: `https://wc26.tinjak.com/team/${params.code}` },
    }
  } catch {
    return { title: "Team" }
  }
}

function Flag({ url, color, cls }: { url?: string; color?: string; cls: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${cls} object-cover ring-1 ring-white/10`} />
  }
  return <span className={`${cls} ring-1 ring-white/10 block`} style={{ background: color || "#1e293b" }} />
}

function PathRow({ label, value }: { label: string; value?: number }) {
  if (value == null) return null
  return (
    <div className="flex items-center gap-3 py-1.5">
      <span className="text-[12.5px] text-slate-300 w-32 sm:w-40 shrink-0">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-white/[0.05] overflow-hidden min-w-0">
        <div className="h-full rounded-full bg-emerald-500/80" style={{ width: `${Math.min(100, Math.max(0, value * 100))}%` }} />
      </div>
      <span className="font-mono text-[12.5px] tabular-nums font-bold text-slate-100 w-12 text-right shrink-0">
        {value >= 0.995 ? "99%+" : value < 0.005 ? "<1%" : `${Math.round(value * 100)}%`}
      </span>
    </div>
  )
}

const POS_ORDER = ["Goalkeeper", "Defender", "Midfielder", "Attacker"]

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: { code: string }
  searchParams: { from?: string }
}) {
  let profile: TeamProfile | null = null
  let proj: TournamentTeam | null = null
  let group: GroupStanding | null = null
  let radar: RadarData | null = null
  let squadRich: Awaited<ReturnType<typeof api.squadRich>> | null = null
  let form: Awaited<ReturnType<typeof api.teamRecentForm>> | null = null
  try {
    const [p, tournament, groups, rad, sq, fm] = await Promise.all([
      api.teamProfile(params.code),
      api.tournament().catch(() => null),
      api.groups().catch(() => null),
      api.radar().catch(() => null),
      api.squadRich(params.code).catch(() => null),
      api.teamRecentForm(params.code).catch(() => null),
    ])
    profile = p
    proj = tournament?.teams.find((t) => t.code === params.code) ?? null
    group = groups?.find((g) => g.teams.some((t) => t.code === params.code)) ?? null
    radar = rad
    squadRich = sq
    form = fm
  } catch {
    /* not found */
  }

  const back = resolveBack(searchParams.from, { href: "/winner", label: "World Cup odds" })

  if (!profile || (profile as { error?: string }).error) {
    return (
      <>
        <TopBar title="Team" backHref={back.href} backLabel={back.label} />
        <p className="text-slate-500 text-sm py-16 text-center px-4">Team not found.</p>
      </>
    )
  }

  const playersByPos: Record<string, NonNullable<typeof squadRich>["players"]> = {}
  if (squadRich?.players) {
    for (const pl of squadRich.players) {
      ;(playersByPos[pl.position] ??= []).push(pl)
    }
  }
  const hasRichSquad = (squadRich?.total ?? 0) > 0

  const teamFrom = `/team/${params.code}`

  return (
    <>
      <TopBar
        title={profile.name}
        subtitle={group ? `Group ${group.group}` : "World Cup 2026"}
        backHref={back.href}
        backLabel={back.label}
      />

      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">

        {/* hero */}
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-5 mb-5 flex items-center gap-4">
          <Flag url={profile.flag_url} color={profile.primary_color} cls="w-16 h-[44px] rounded shrink-0" />
          <div className="min-w-0">
            <h1 className="text-[22px] font-black text-white leading-tight">{profile.name}</h1>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {profile.manager && <>Coach {profile.manager} · </>}
              Rating {Math.round(profile.elo)}
              {profile.fifa_ranking ? ` · FIFA #${profile.fifa_ranking}` : ""}
            </p>
          </div>
        </div>

        {/* the model's path */}
        {proj && (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/80 mb-3">The model&apos;s outlook</p>
            <PathRow label="Win the group" value={proj.p_first} />
            <div className="border-t border-white/[0.05] my-3" />
            {proj.p_title != null ? (
              <SurvivalFunnel team={proj} />
            ) : (
              <>
                <PathRow label="Reach the last 32" value={proj.p_advance} />
                <p className="text-[11px] text-slate-600 mt-2">From {(proj.exp_points ?? 0).toFixed(1)} expected group points across 20,000 simulations.</p>
              </>
            )}
          </div>
        )}

        {/* strengths radar */}
        {radar?.teams?.[params.code] && (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-1">Team strengths</p>
            <TeamRadar axes={radar.axes} teamA={radar.teams[params.code]} />
          </div>
        )}

        {/* recent form */}
        {form && (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Recent form</p>
            <FormStrip games={form.form} teamCode={params.code} />
          </div>
        )}

        {/* fixtures */}
        {profile.upcoming_fixtures.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Group fixtures</p>
            <div className="space-y-2">
              {profile.upcoming_fixtures.map((fx) => (
                <Link
                  key={fx.match_id}
                  href={`/match/${fx.match_id}?from=${encodeURIComponent(teamFrom)}`}
                  className="flex items-center gap-3 rounded-xl border border-edge bg-surface-2 shadow-e1 px-3.5 py-2.5 hover:border-emerald-500/30 transition-colors"
                >
                  <span className="text-[11px] text-slate-600 w-16 shrink-0">MD{fx.matchday}</span>
                  <span className="text-[11px] text-slate-500 shrink-0">{fx.is_home ? "vs" : "at"}</span>
                  <Flag url={fx.opponent_flag} cls="w-6 h-[18px] rounded-[2px] shrink-0" />
                  <span className="text-[13px] font-semibold text-slate-100 flex-1 truncate">{fx.opponent}</span>
                  <span className="text-[11px] text-slate-500 shrink-0 hidden sm:block">{fx.kickoff && <KickoffTime iso={fx.kickoff} />}</span>
                  <ArrowRight size={14} className="text-slate-600 shrink-0" />
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* group standing */}
        {group && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Group {group.group}</p>
            <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
              {group.teams.map((t, i) => (
                <Link
                  key={t.code}
                  href={`/team/${t.code}?from=${encodeURIComponent(teamFrom)}`}
                  className={[
                    "flex items-center gap-3 px-3.5 py-2 text-[12.5px] border-b border-white/[0.04] last:border-0 hover:bg-surface-1 transition-colors",
                    t.code === params.code ? "bg-emerald-950/30" : "",
                  ].join(" ")}
                >
                  <span className="font-mono text-slate-600 w-4">{i + 1}</span>
                  <Flag url={t.flag_url} cls="w-5 h-[15px] rounded-[2px] shrink-0" />
                  <span className={`flex-1 truncate ${t.code === params.code ? "text-white font-bold" : "text-slate-300"}`}>{t.name}</span>
                  <span className="font-mono text-slate-500 tabular-nums w-8 text-right">{t.played}P</span>
                  <span className="font-mono text-white tabular-nums w-8 text-right font-bold">{t.points}</span>
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* squad — rich photo grid when harvested, fallback to text */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">
          Squad{hasRichSquad ? ` (${squadRich!.total})` : ""}
        </p>
        {hasRichSquad ? (
          <div className="space-y-3">
            {POS_ORDER.filter((pos) => playersByPos[pos]?.length).map((pos) => (
              <div key={pos}>
                <p className="text-[10px] font-bold uppercase tracking-wider text-slate-600 mb-1.5 px-1">{pos}s</p>
                <div className="grid sm:grid-cols-2 gap-2">
                  {playersByPos[pos].map((pl) => (
                    <PlayerCard key={pl.player_id} player={pl} teamCode={params.code} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : profile.squad && profile.squad.length > 0 ? (
          <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 p-3.5">
            <p className="text-[11px] text-slate-500 mb-2">Squad data still loading. Players will show photos and season stats once harvested.</p>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {profile.squad.map((pl) => (
                <span key={pl.name} className="text-[12.5px] text-slate-300">
                  {pl.number != null && <span className="text-slate-600 font-mono mr-1">{pl.number}</span>}
                  {pl.name}
                </span>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-[12px] text-slate-600 rounded-xl border border-edge bg-surface-2 shadow-e1 p-3.5">
            Squad will appear once it&apos;s harvested. Check back shortly.
          </p>
        )}
      </div>
    </>
  )
}
