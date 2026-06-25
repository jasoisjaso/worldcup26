import type { Metadata } from "next"
import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { MarketsSheet } from "@/components/match/MarketsSheet"
import { ScoreHeatmap } from "@/components/match/ScoreHeatmap"
import { GoalsDistribution } from "@/components/viz/GoalsDistribution"
import { TeamRadar } from "@/components/viz/TeamRadar"
import { MatchVerdict } from "@/components/match/MatchVerdict"
import { ModelVsMarket } from "@/components/match/ModelVsMarket"
import { VerdictBlock } from "@/components/match/VerdictBlock"
import { TrustStrip } from "@/components/match/TrustStrip"
import { BackingTab } from "@/components/match/BackingTab"
import { LiveBanner } from "@/components/match/LiveBanner"
import { FactorContributions } from "@/components/match/FactorContributions"
import { KeyPlayersToWatch } from "@/components/match/KeyPlayersToWatch"
import { DataProvenance } from "@/components/match/DataProvenance"
import { SwingChart } from "@/components/match/SwingChart"
import { HeadToHead } from "@/components/match/HeadToHead"
import { PreMatchBrief } from "@/components/match/PreMatchBrief"
import { MatchCommunityBrief } from "@/components/match/MatchCommunityBrief"
import { CommunityVsModel } from "@/components/match/CommunityVsModel"
import { MatchRecap } from "@/components/match/MatchRecap"
import { KickoffTime } from "@/components/common/KickoffTime"
import { ShareButton } from "@/components/common/ShareButton"
import { EngagementMarker } from "@/components/common/EngagementMarker"
import { DownloadCardButton } from "@/components/match/DownloadCardButton"
import { api } from "@/lib/api"
import { resolveBack } from "@/lib/back-nav"
import type { Match, MatchPrediction, MarketsSheet as Sheet, RadarData, KeyPlayers } from "@/lib/types"

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
  searchParams: { from?: string; backing?: string }
}) {
  let match: Match | null = null
  let prediction: MatchPrediction | null = null
  let sheet: Sheet | null = null
  let radar: RadarData | null = null
  let h2hData: any = null
  let recap: Awaited<ReturnType<typeof api.matchRecap>> | null = null
  let preMatch: Awaited<ReturnType<typeof api.preMatchContext>> | null = null
  let keyPlayers: KeyPlayers | null = null
  // Tournament projection. Used to surface both teams' current advance %
  // alongside the kickoff/venue line on the match page header. Tap-through
  // is the existing 'Group X standings ->' link.
  let tournament: Awaited<ReturnType<typeof api.tournament>> | null = null
  try {
    ;[match, prediction, sheet, radar, h2hData, recap, preMatch, keyPlayers, tournament] = await Promise.all([
      api.match(params.id),
      api.prediction(params.id).catch(() => null),
      api.markets(params.id).catch(() => null),
      api.radar().catch(() => null),
      api.h2h(params.id).catch(() => null),
      api.matchRecap(params.id).catch(() => null),
      api.preMatchContext(params.id).catch(() => null),
      api.keyPlayers(params.id).catch(() => null),
      api.tournament().catch(() => null),
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
      <EngagementMarker />
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
          <p className="text-[11px] text-slate-500 text-center mb-2">
            <KickoffTime iso={match.kickoff} /> · {match.venue}
          </p>
          {/* Group standings deeplink + per-team advance %. One tap from match
              to the group table, with both teams' qualification odds inline so
              the stakes of THIS match are visible at a glance. */}
          {(() => {
            const homeProj = tournament?.teams?.find((t) => t.code === match.home.code)
            const awayProj = tournament?.teams?.find((t) => t.code === match.away.code)
            const advPct = (p: number | undefined) =>
              p == null ? null : `${Math.round(p * 100)}%`
            const homeAdv = advPct(homeProj?.p_advance)
            const awayAdv = advPct(awayProj?.p_advance)
            return (
              <div className="text-[11px] text-center mb-3 flex items-center justify-center flex-wrap gap-x-3 gap-y-1">
                <Link
                  href={`/groups?focus=${match.group}`}
                  className="text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                  Group {match.group} standings →
                </Link>
                <Link
                  href="/bracket"
                  className="text-emerald-400 hover:text-emerald-300 transition-colors"
                >
                  Bracket →
                </Link>
                {(homeAdv || awayAdv) && (
                  <span className="text-slate-500 font-mono tabular-nums">
                    {homeAdv && <span>{match.home.code.toUpperCase()} <span className="text-slate-300">{homeAdv}</span></span>}
                    {homeAdv && awayAdv && <span className="text-slate-700"> · </span>}
                    {awayAdv && <span>{match.away.code.toUpperCase()} <span className="text-slate-300">{awayAdv}</span></span>}
                    <span className="text-slate-700"> to advance</span>
                  </span>
                )}
              </div>
            )
          })()}
          <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
            {/* Home team panel: tappable, navigates to the team page so users can
                drill from a match into the team profile without going via search.
                User flag (2026-06-21): "I cant actually select bosnia or the other
                team [from the match card]". */}
            <Link
              href={`/team/${match.home.code}?from=${encodeURIComponent(`/match/${params.id}`)}`}
              className="text-center group rounded-lg p-1 -m-1 hover:bg-surface-3/40 transition-colors"
            >
              <Flag url={match.home.flag_url} color={match.home.primary_color} />
              <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight group-hover:text-emerald-300 transition-colors">{match.home.name}</p>
              {prediction && <p className="text-[26px] font-black text-emerald-400 tabular-nums leading-none mt-1">{Math.round(prediction.home_win * 100)}%</p>}
            </Link>
            <div className="text-center px-2">
              {complete ? (
                <>
                  <p className="text-[9px] text-slate-600 font-bold uppercase tracking-widest">FT</p>
                  <p className="text-[24px] font-black text-white tabular-nums">{match.actual_score!.home}&ndash;{match.actual_score!.away}</p>
                  {/* HT line — only shows when the backfill populated it.
                      User asked for FT + HT to be separated (2026-06-21). */}
                  {match.ht_score && (
                    <p className="text-[10px] font-mono text-slate-500 tabular-nums mt-1">
                      HT {match.ht_score.home}&ndash;{match.ht_score.away}
                    </p>
                  )}
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
            {/* Away team panel: mirror of the home Link above. */}
            <Link
              href={`/team/${match.away.code}?from=${encodeURIComponent(`/match/${params.id}`)}`}
              className="text-center group rounded-lg p-1 -m-1 hover:bg-surface-3/40 transition-colors"
            >
              <Flag url={match.away.flag_url} color={match.away.primary_color} />
              <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight group-hover:text-orange-300 transition-colors">{match.away.name}</p>
              {prediction && <p className="text-[26px] font-black text-orange-400 tabular-nums leading-none mt-1">{Math.round(prediction.away_win * 100)}%</p>}
            </Link>
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

          {/* Data provenance — where the numbers came from + how fresh. Builds
              trust; pure render off the prediction payload. Hidden when complete. */}
          {prediction && !complete && <DataProvenance p={prediction} />}
        </div>

        {/* Live banner. Self-suppresses when match isn't in play. Polls
            /api/live/match/<id>/live every 20s and shows current score +
            updated win prob vs the pre-kickoff number. Calm: same height in
            all states, no flashing on updates (see in-play UX research). */}
        {prediction && !complete && (() => {
          const mkt = (key: string) =>
            prediction.markets?.find((x) => x.market === key)?.market_implied ?? null
          return (
            <LiveBanner
              matchId={params.id}
              homeName={match.home.name}
              awayName={match.away.name}
              kickoffProbs={{
                home_win: prediction.home_win,
                draw: prediction.draw,
                away_win: prediction.away_win,
              }}
              marketImplied={{
                home_win: mkt("home_win"),
                draw: mkt("draw"),
                away_win: mkt("away_win"),
              }}
            />
          )
        })()}

        {/* Backing X toggle. Tapping a team name switches the verdict block
            for the BackingTab three-card pattern. Active state echoed in the
            ?backing= query param so deeplinks work (/team/X follow-bell will
            link straight into the right backing view). */}
        {prediction && !complete && (() => {
          const backing = searchParams.backing === "home" ? "home"
                        : searchParams.backing === "away" ? "away"
                        : null
          const baseHref = `/match/${params.id}`
          const fromQ = searchParams.from ? `&from=${encodeURIComponent(searchParams.from)}` : ""
          return (
            <>
              <div className="mb-4 flex items-center gap-2 px-1">
                <span className="text-[10px] uppercase tracking-widest text-slate-600">I&apos;m backing</span>
                <a
                  href={`${baseHref}?backing=home${fromQ}`}
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-colors ${
                    backing === "home"
                      ? "bg-emerald-500/20 border-emerald-600/40 text-emerald-300"
                      : "bg-surface-2 border-edge text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {match.home.name}
                </a>
                <a
                  href={`${baseHref}?backing=away${fromQ}`}
                  className={`text-[11px] font-semibold px-2.5 py-1 rounded-full border transition-colors ${
                    backing === "away"
                      ? "bg-emerald-500/20 border-emerald-600/40 text-emerald-300"
                      : "bg-surface-2 border-edge text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {match.away.name}
                </a>
                {backing && (
                  <a href={`${baseHref}${fromQ ? `?${fromQ.slice(1)}` : ""}`}
                     className="text-[10px] text-slate-500 hover:text-slate-300 ml-1">
                    Clear
                  </a>
                )}
              </div>
              {backing ? (
                <BackingTab prediction={prediction} match={match} side={backing} />
              ) : (
                <VerdictBlock prediction={prediction} match={match} complete={complete} />
              )}
            </>
          )
        })()}

        {/* Trust strip — hit rate · sample · ROI · CLV. SSR component, fetches
            /history/stats server-side and renders silently when there's no
            settled sample yet. Layer 1.5 of the taste pass. */}
        {!complete && <TrustStrip />}

        {/* Match recap — goals, cards, stats, MOTM, lineups. Hidden when the
            match has no events / stats / lineups yet (pre-match). */}
        {recap && recap.has_content && (
          <div className="mb-5">
            <MatchRecap recap={recap} />
          </div>
        )}

        {/* Pre-match brief — stakes, form-vs-opponent, season averages,
            H2H, absences, model-swing-from-absences. Replaces the older
            standalone HeadToHead block (now embedded inside the brief).
            Pre-match only; for completed matches we skip the stakes line
            but the comparison + form + h2h still read as a useful summary. */}
        {preMatch && (
          <PreMatchBrief
            ctx={preMatch}
            homeName={match.home.name}
            awayName={match.away.name}
            homeCode={match.home.code}
            awayCode={match.away.code}
          />
        )}

        {/* Community-vs-model divergence read — surfaces only when one side's
            community sentiment meaningfully disagrees with the model's win
            probability (the StockTwits attention-vs-price divergence pattern,
            ported to match prediction). Hides when both sides have no
            sentiment signal or both are mixed. */}
        {prediction && !complete && (
          <CommunityVsModel
            homeCode={match.home.code}
            awayCode={match.away.code}
            homeName={match.home.name}
            awayName={match.away.name}
            homeWin={prediction.home_win}
            awayWin={prediction.away_win}
            drawProb={prediction.draw}
          />
        )}

        {/* Community brief — Reddit / web chatter about this specific matchup,
            harvested by scripts/harvest_match_briefs.py on the VPS into
            /data/match-briefs.json. Returns null when no data exists for this
            match (no fixture in next 36h, harvest hasn't run yet, etc.).
            Hidden on completed matches — pre-match chatter goes stale once
            the result is known; post-match reactions live in <MatchRecap>. */}
        {!complete && <MatchCommunityBrief matchId={params.id} />}

        {/* Live swing chart — shows only when a live tick has been written for this
            match. Component handles its own empty/pre-match/live/complete states. */}
        <div className="mb-5">
          <SwingChart matchId={params.id} homeName={match.home.name} awayName={match.away.name} />
        </div>

        {/* Plain-language model read — kept for COMPLETE matches as a post-match
            summary ("what we thought going in"). Pre-match this is superseded
            by the VerdictBlock above, so we suppress it to avoid two competing
            "model says" cards stacked. */}
        {prediction && complete && (
          <div className="mb-5">
            <MatchVerdict p={prediction} homeName={match.home.name} awayName={match.away.name} />
          </div>
        )}

        {/* why factors — quantified bars from prediction.context multipliers,
            falls back to flat chips when context is empty (early matches with
            no rest/travel/lineup deltas yet). */}
        {prediction && (prediction.why_factors.length > 0 || prediction.context) && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Why the model leans this way</p>
            <FactorContributions context={prediction.context} factors={prediction.why_factors} />
          </div>
        )}

        {/* key players to watch — top G/90 + A/90 per side from the per-90
            club-season dataset already loaded server-side. Hidden when neither
            squad has resolvable per-90 rows. */}
        {keyPlayers && (keyPlayers.home.length > 0 || keyPlayers.away.length > 0) && (
          <div className="mb-5">
            <KeyPlayersToWatch
              home={keyPlayers.home}
              away={keyPlayers.away}
              homeName={match.home.name}
              awayName={match.away.name}
              attribution={keyPlayers.attribution}
            />
          </div>
        )}

        {/* Model vs market — where we disagree with the bookie, the core
            "informed decision" signal. Self-suppresses for completed matches
            (nothing to bet) and when odds are placeholder estimates. */}
        {prediction && !complete && (
          <div className="mb-5">
            <ModelVsMarket p={prediction} />
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
