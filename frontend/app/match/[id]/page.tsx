import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { MarketsSheet } from "@/components/match/MarketsSheet"
import { ScoreHeatmap } from "@/components/match/ScoreHeatmap"
import { GoalsDistribution } from "@/components/viz/GoalsDistribution"
import { TeamRadar } from "@/components/viz/TeamRadar"
import { MatchVerdict } from "@/components/match/MatchVerdict"
import { SwingChart } from "@/components/match/SwingChart"
import { HeadToHead } from "@/components/match/HeadToHead"
import { MatchRecap } from "@/components/match/MatchRecap"
import { KickoffTime } from "@/components/common/KickoffTime"
import { ShareButton } from "@/components/common/ShareButton"
import { DownloadCardButton } from "@/components/match/DownloadCardButton"
import { api } from "@/lib/api"
import { resolveBack } from "@/lib/back-nav"
import type { Match, MatchPrediction, MarketsSheet as Sheet, RadarData } from "@/lib/types"

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  try {
    const m = await api.match(params.id)
    const title = `${m.home.name} vs ${m.away.name}: Prediction & Fair Odds`
    const description = `Model prediction, win probabilities and fair odds across 30+ betting markets for ${m.home.name} vs ${m.away.name} at the 2026 World Cup.`
    // Per-match OG card — the Satori-rendered 1200x630 PNG that already lives at
    // /share/match-wp/[matchId]/opengraph-image. Falls back to the site-wide card
    // if the per-match data isn't there yet (route returns a branded default).
    const ogUrl = `https://wc26.tinjak.com/share/match-wp/${params.id}/opengraph-image`
    return {
      title,
      description,
      alternates: { canonical: `https://wc26.tinjak.com/match/${params.id}` },
      openGraph: {
        title,
        description,
        url: `https://wc26.tinjak.com/match/${params.id}`,
        type: "article",
        images: [{ url: ogUrl, width: 1200, height: 630, alt: `${m.home.name} vs ${m.away.name} win probability` }],
      },
      twitter: {
        card: "summary_large_image",
        title,
        description,
        images: [ogUrl],
      },
    }
  } catch {
    return { title: "Match prediction" }
  }
}

function Flag({ url, color, size = "w-9 h-[26px]" }: { url?: string; color?: string; size?: string }) {
  if (url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={url} alt="" className={`${size} rounded object-cover ring-1 ring-white/10 mx-auto`} />
  }
  return <span className={`${size} rounded ring-1 ring-white/10 mx-auto block`} style={{ background: color || "#1e293b" }} />
}

export default async function MatchPage({
  params,
  searchParams,
}: {
  params: { id: string }
  searchParams: { from?: string }
}) {
  let match: Match | null = null
  let prediction: MatchPrediction | null = null
  let sheet: Sheet | null = null
  let radar: RadarData | null = null
  let h2hData: any = null
  let recap: Awaited<ReturnType<typeof api.matchRecap>> | null = null
  try {
    ;[match, prediction, sheet, radar, h2hData, recap] = await Promise.all([
      api.match(params.id),
      api.prediction(params.id).catch(() => null),
      api.markets(params.id).catch(() => null),
      api.radar().catch(() => null),
      api.h2h(params.id).catch(() => null),
      api.matchRecap(params.id).catch(() => null),
    ])
  } catch {
    /* match not found */
  }

  const back = resolveBack(searchParams.from, { href: "/", label: "All matches" })

  if (!match) {
    return (
      <>
        <TopBar title="Match" backHref={back.href} backLabel={back.label} />
        <p className="text-slate-500 text-sm py-16 text-center px-4">Match not found.</p>
      </>
    )
  }

  const complete = match.status === "complete" && match.actual_score != null

  // Structured data so search engines can render this as a rich sports-event result.
  const ld = {
    "@context": "https://schema.org",
    "@type": "SportsEvent",
    name: `${match.home.name} vs ${match.away.name}`,
    sport: "Association football",
    startDate: match.kickoff,
    eventStatus: complete ? "https://schema.org/EventCompleted" : "https://schema.org/EventScheduled",
    ...(match.venue ? { location: { "@type": "Place", name: match.venue } } : {}),
    competitor: [
      { "@type": "SportsTeam", name: match.home.name },
      { "@type": "SportsTeam", name: match.away.name },
    ],
    superEvent: { "@type": "SportsEvent", name: "2026 FIFA World Cup" },
    description: `Model prediction, win probabilities and fair odds for ${match.home.name} vs ${match.away.name} at the 2026 FIFA World Cup.`,
  }

  return (
    <>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(ld) }} />
      <TopBar
        title={`${match.home.name} vs ${match.away.name}`}
        subtitle={`Group ${match.group} · Matchday ${match.matchday}`}
        backHref={back.href}
        backLabel={back.label}
        // User feedback (2026-06-21): match top bar had Download + Share + Search +
        // Timezone all crammed next to truncated team names. Moved Download down
        // beside the probability bar (its natural context) and keep Share here.
        // Share goes icon-only on small screens so the team names actually breathe.
        action={
          <ShareButton
            title={`${match.home.name} vs ${match.away.name} prediction`}
            text={
              prediction
                ? `${match.home.name} ${Math.round(prediction.home_win * 100)}% · Draw ${Math.round(prediction.draw * 100)}% · ${match.away.name} ${Math.round(prediction.away_win * 100)}% · WC2026 model prediction & fair odds`
                : `${match.home.name} vs ${match.away.name} · WC2026 model prediction`
            }
            url={`https://wc26.tinjak.com/match/${params.id}`}
            label="Share"
            compactOnMobile
          />
        }
      />

      <div className="max-w-3xl mx-auto px-3 sm:px-5 py-5">

        {/* header */}
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-5 mb-5">
          <p className="text-[11px] text-slate-500 text-center mb-3">
            <KickoffTime iso={match.kickoff} /> · {match.venue}
          </p>
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            <div className="text-center">
              <Flag url={match.home.flag_url} color={match.home.primary_color} />
              <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight">{match.home.name}</p>
              {prediction && <p className="text-[26px] font-black text-emerald-400 tabular-nums leading-none mt-1">{Math.round(prediction.home_win * 100)}%</p>}
            </div>
            <div className="text-center px-2">
              {complete ? (
                <>
                  <p className="text-[9px] text-slate-600 font-bold uppercase tracking-widest">FT</p>
                  <p className="text-[24px] font-black text-white tabular-nums">{match.actual_score!.home}&ndash;{match.actual_score!.away}</p>
                </>
              ) : (
                <>
                  <p className="text-[10px] text-slate-700 font-bold tracking-widest">VS</p>
                  {prediction && (
                    <>
                      <p className="text-[15px] font-bold text-slate-400 tabular-nums mt-1">{Math.round(prediction.draw * 100)}%</p>
                      <p className="text-[8px] text-slate-700 uppercase tracking-wide">draw</p>
                    </>
                  )}
                </>
              )}
            </div>
            <div className="text-center">
              <Flag url={match.away.flag_url} color={match.away.primary_color} />
              <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight">{match.away.name}</p>
              {prediction && <p className="text-[26px] font-black text-orange-400 tabular-nums leading-none mt-1">{Math.round(prediction.away_win * 100)}%</p>}
            </div>
          </div>

          {prediction && (
            <div className="mt-4 flex h-2 rounded-full overflow-hidden bg-surface-2">
              <div className="bg-emerald-500" style={{ width: `${prediction.home_win * 100}%` }} />
              <div className="bg-slate-600" style={{ width: `${prediction.draw * 100}%` }} />
              <div className="bg-orange-500" style={{ width: `${prediction.away_win * 100}%` }} />
            </div>
          )}

          {/* Download card lives here (its natural home: right under the prediction
              it represents) instead of in the TopBar — keeps the action row free
              for Share and the team names readable. */}
          <div className="mt-3 flex justify-center">
            <DownloadCardButton
              matchId={params.id}
              homeName={match.home.name}
              awayName={match.away.name}
            />
          </div>
        </div>

        {/* Match recap — goals, cards, stats, MOTM, lineups. Hidden when the
            match has no events / stats / lineups yet (pre-match). */}
        {recap && recap.has_content && (
          <div className="mb-5">
            <MatchRecap recap={recap} />
          </div>
        )}

        {/* Head-to-head */}
        {h2hData && h2hData.total_meetings > 0 && (
          <div className="mb-5">
            <HeadToHead data={h2hData} homeName={match.home.name} awayName={match.away.name} />
          </div>
        )}

        {/* Live swing chart — shows only when a live tick has been written for this
            match. Component handles its own empty/pre-match/live/complete states. */}
        <div className="mb-5">
          <SwingChart matchId={params.id} homeName={match.home.name} awayName={match.away.name} />
        </div>

        {/* plain-language model read */}
        {prediction && (
          <div className="mb-5">
            <MatchVerdict p={prediction} homeName={match.home.name} awayName={match.away.name} />
          </div>
        )}

        {/* why factors */}
        {prediction && prediction.why_factors.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Why the model leans this way</p>
            <div className="flex flex-wrap gap-1.5">
              {prediction.why_factors.map((f, i) => (
                <span
                  key={i}
                  className={[
                    "text-[11px] px-2.5 py-1 rounded-md border",
                    f.direction === "positive" ? "border-emerald-900/60 bg-emerald-950/30 text-emerald-300"
                      : f.direction === "negative" ? "border-rose-900/60 bg-rose-950/30 text-rose-300"
                      : "border-edge bg-surface-2 text-slate-400",
                  ].join(" ")}
                >
                  {f.label}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* analytics dashboard: heatmap + goals distribution + team radar */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Match analysis</p>
        <div className="grid md:grid-cols-2 gap-4 mb-5">
          {sheet?.score_grid && (
            <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5">
              <ScoreHeatmap grid={sheet.score_grid} homeName={match.home.name} awayName={match.away.name} />
            </div>
          )}
          {sheet?.score_grid && (
            <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5">
              <GoalsDistribution grid={sheet.score_grid.grid} />
            </div>
          )}
          {radar?.teams?.[match.home.code] && radar?.teams?.[match.away.code] && (
            <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5 md:col-span-2">
              <p className="text-[10px] font-bold uppercase tracking-[0.16em] text-slate-500 mb-1">Team comparison</p>
              <TeamRadar axes={radar.axes} teamA={radar.teams[match.home.code]} teamB={radar.teams[match.away.code]} />
            </div>
          )}
        </div>

        {/* markets sheet */}
        <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Fair odds for every market</p>
        {sheet ? (
          <MarketsSheet sheet={sheet} />
        ) : (
          <p className="text-[12px] text-slate-600">Markets unavailable for this match right now.</p>
        )}
      </div>
    </>
  )
}
