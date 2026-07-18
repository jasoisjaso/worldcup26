// frontend/components/match/FinalsBettingGuide.tsx
// Betting guide for the final two matches of the tournament.
// EVERY number here is checked against the live model prediction on the VPS
// (win probs, xG/lambda, top scorelines, market-implied) and every injury line
// against team-news reporting. No fabricated injuries, no invented prices.
// Last verified 18 July (server clock): model pull + team-news sweep.

interface Pick {
  market: string
  selection: string
  odds: string
  confidence: string
  stake: string
  why: string
  tag: "BEST BET" | "VALUE" | "CONTRARIAN" | "AVOID"
}

interface FactorItem {
  team: string
  text: string
  impact: "positive" | "negative" | "neutral"
}

interface MatchGuide {
  title: string
  kickoff: string
  venue: string
  modelRead: string
  picks: Pick[]
  factors: FactorItem[]
  bottomLine: string
}

const THIRD_PLACE: MatchGuide = {
  title: "3rd Place: France vs England",
  kickoff: "Sat 18 July · 10pm BST",
  venue: "Hard Rock Stadium, Miami",
  modelRead:
    "France 56% · Draw 28% · England 16%. Model xG: France 1.59, England 0.71. Most likely scores: 1-0 (15%), 1-1 (13%), 2-0 (13%), 0-0 (12%). Under 2.5 at 60%, BTTS No at 58%. A low-scoring France win is the model's clear central case.",
  picks: [
    {
      market: "Match Result",
      selection: "France to win",
      odds: "$1.86",
      confidence: "56% model vs ~54% priced-in · +4% EV",
      stake: "~1.2% of bankroll ($12 on $1,000) — quarter-Kelly",
      why: "The clearest edge on the board, but a modest one: the model rates France 56% and the price implies about 54%. That's roughly +4% value at $1.86. England managed just 0.71 model xG — they struggle to score — and Tuchel has said outright that 'nobody wants to play' this game, so expect a heavily rotated, low-intensity England. It's still a dead rubber, so keep the stake small.",
      tag: "BEST BET",
    },
    {
      market: "Result + Clean Sheet",
      selection: "France to win to nil",
      odds: "~$2.75 fair (shop around)",
      confidence: "France clean sheet 49% · top scores 1-0 (15%) and 2-0 (13%)",
      stake: "0.5-1% of bankroll (bigger payout, lower hit rate)",
      why: "The model's two most likely scorelines are both France shut-outs. France to keep a clean sheet is 49% (England 0.71 xG), and France winning to nil comes out around 36% — fair odds near $2.75. A cleaner, higher-payout way to back the same read than the straight win. If you'd rather, France win + Under 2.5 as a combo covers the 1-0 and 2-0 specifically.",
      tag: "VALUE",
    },
    {
      market: "Anytime Goalscorer",
      selection: "Mbappe to score",
      odds: "~$1.70-1.85 (market)",
      confidence: "Golden Boot chase — 8 goals, level with Messi",
      stake: "small — narrative lean, not a model edge",
      why: "Mbappe is tied with Messi on 8 for the Golden Boot and this is the last game of his tournament — he'll play every minute and take every chance. Treat it as a motivation play rather than a hard model number: the model doesn't publish a per-player anytime price, so size it small and only take it if the market price is 1.75+.",
      tag: "VALUE",
    },
    {
      market: "Total Goals",
      selection: "Over / Under 2.5",
      odds: "—",
      confidence: "Model says Under 2.5 (60%)",
      stake: "0 — sit it out",
      why: "The model leans Under, but the fair price on Under (~$1.65) is shorter than most books offer, so there's no clean value either way. Layer on Saliba's absence and wholesale rotation on both sides and the total becomes a genuine coin-flip in practice. No edge in either direction — leave it.",
      tag: "AVOID",
    },
    {
      market: "Match Result",
      selection: "England to win",
      odds: "$3.85",
      confidence: "16% model prob · 0.71 model xG",
      stake: "0",
      why: "16% win probability and just 0.71 expected goals. Reece James limped off in the semi and is a major doubt, Jordan Henderson is sidelined with a wrist injury, and Tuchel is rotating heavily in a game he's admitted nobody wants to play. Not a side to back.",
      tag: "AVOID",
    },
  ],
  factors: [
    {
      team: "France",
      text: "William Saliba OUT — back injury, walked off the semi vs Spain ('my back is gone'). France's first-choice centre-back; Lacroix or Konsa expected to step in.",
      impact: "negative",
    },
    {
      team: "France",
      text: "Brice Samba (backup keeper) also out with a calf issue. Deschamps, in effectively his last game in charge, is expected to rotate heavily.",
      impact: "neutral",
    },
    {
      team: "France",
      text: "Mbappe (8 goals) is chasing the Golden Boot and will want every minute — the one certainty amid the rotation.",
      impact: "positive",
    },
    {
      team: "England",
      text: "Reece James forced off injured (muscle) late in the semi vs Argentina — a major doubt. Djed Spence or Trevoh Chalobah in contention to cover.",
      impact: "negative",
    },
    {
      team: "England",
      text: "Jordan Henderson sidelined with a wrist injury.",
      impact: "negative",
    },
    {
      team: "England",
      text: "Rice, Kane and Bellingham have carried heavy minutes all tournament, and Tuchel has signalled 'significant changes' — several are likely to be rested.",
      impact: "neutral",
    },
    {
      team: "England",
      text: "Tuchel has openly said 'nobody wants to play' the third-place game — expect a much-changed, low-intensity side.",
      impact: "neutral",
    },
    {
      team: "Model",
      text: "The model's win probabilities don't ingest late lineup news — Saliba's absence and England's rotation aren't baked into the numbers, so treat the injury picture as a manual overlay on top of the model.",
      impact: "neutral",
    },
  ],
  bottomLine:
    "Back France to win at ~$1.86 — a small but real edge (56% model vs ~54% priced), and England can't score (0.71 xG) in a game Tuchel says nobody wants to play. For a bigger payout, France to nil (~$2.75) covers the model's top two scorelines, 1-0 and 2-0. Skip the total — the model's Under is priced fairly, not generously. Keep stakes modest: it's a dead rubber with heavy rotation on both sides.",
}

const FINAL: MatchGuide = {
  title: "Final: Spain vs Argentina",
  kickoff: "Sun 19 July · 8pm BST",
  venue: "MetLife Stadium, East Rutherford NJ",
  modelRead:
    "Spain 44% · Draw 30% · Argentina 26%. Model xG: Spain 1.49, Argentina 1.04. Most likely scores: 1-1 (14%), 1-0 (10%), 0-0 (10%), 2-1 (9%). Under 2.5 at 55%, BTTS a near coin-flip (Yes 52%). BIG CAVEAT: the two sub-models disagree hard — form-based Dixon-Coles has Spain 61%, ELO ratings have Argentina 46%. Lower confidence than the bronze final.",
  picks: [
    {
      market: "Match Result (90 min)",
      selection: "Spain to win",
      odds: "$2.30 (Pinnacle)",
      confidence: "44% model vs ~43% priced-in · thin +2% edge",
      stake: "~0.4% of bankroll ($4 on $1,000) — low confidence",
      why: "Spain are the model's pick and they beat France 2-0 with a clean sheet in the semi. But the edge is razor-thin (~+2%) and the two sub-models split hard — form says Spain 61%, ELO says Argentina. That disagreement is why the suggested stake is tiny. If you want the safer expression, Spain in the outright 'to lift the trophy' market shortens the price but banks the extra-time and shootout coverage.",
      tag: "BEST BET",
    },
    {
      market: "To Lift the Trophy",
      selection: "Argentina (outright, not 90-min result)",
      odds: "Outright market — shop around",
      confidence: "26% to win in 90, but a knockout — ET & pens are live",
      stake: "1 small unit if you fancy Argentina",
      why: "If you fancy Argentina, back them to WIN THE CUP, not the 90-minute result. They're only 26% in normal time, but this is a one-off knockout: extra time and penalties are on the table, and our ELO sub-model actually rates Argentina ahead (46% vs Spain's 25%). Full squad, no injuries, and their bench — De Paul, Nico Gonzalez, Lautaro Martinez — swung the semi vs England.",
      tag: "CONTRARIAN",
    },
    {
      market: "Total Goals",
      selection: "Over 2.5",
      odds: "$2.25",
      confidence: "45% model vs ~44% priced-in · +4% EV",
      stake: "small — the model's biggest single edge here",
      why: "Quietly, Over 2.5 is the one market where the model sees value at the current price (~+4% EV at $2.25). It's marginal, and it cuts against finals history — only about 2 of the last 8 finals went over 2.5 in 90 minutes. So it's a small, model-led lean, not a conviction bet. If you trust the history more than the model, the flip side (Under) is fine but has no edge at the ~$1.62 books are offering.",
      tag: "VALUE",
    },
    {
      market: "Result + Clean Sheet",
      selection: "Spain to win to nil",
      odds: "~$4.40 fair (shop around)",
      confidence: "Spain 1-0 (10%) and 2-0 (9%) are the 2nd/3rd likeliest scores",
      stake: "0.5 unit (bigger payout, lower hit rate)",
      why: "Spain kept France out in the semi; if they win this in 90 it's likely a tight 1-0 or 2-0. Spain to nil comes out around 22% — fair odds near $4.40 — a bigger-payout play that fits the model's scoreline shape. Small stake.",
      tag: "VALUE",
    },
    {
      market: "Match Result (90 min)",
      selection: "Draw (the tie goes long)",
      odds: "$3.00",
      confidence: "30% model · 1-1 is the single likeliest scoreline",
      stake: "1 unit if you think it goes the distance",
      why: "The contrarian play. 1-1 (14%) is the most likely single scoreline, and five of the last eight World Cup finals went to extra time. If you think this one is cagey and goes long, the 90-minute draw at $3.00 is the bet — and it pairs naturally with backing Argentina in the outright, since a draw after 90 keeps their shootout equity alive.",
      tag: "CONTRARIAN",
    },
  ],
  factors: [
    {
      team: "Spain",
      text: "Lamine Yamal trained apart with strapping on his left thigh — but the federation and De la Fuente played the scare down and every report has him expected to start. Worth checking the confirmed XI, but a minor concern, not a swing factor.",
      impact: "neutral",
    },
    {
      team: "Spain",
      text: "Otherwise a clean bill of health after beating France 2-0. Pedri has been benched two games running (Rodri + Fabian Ruiz running midfield); Nico Williams is fit again as a left-side option.",
      impact: "positive",
    },
    {
      team: "Argentina",
      text: "No injuries reported, full squad available. Messi (8 goals, level with Mbappe for the Golden Boot) gets one more World Cup final.",
      impact: "positive",
    },
    {
      team: "Argentina",
      text: "Scaloni's bench swung the semi — De Paul, Nico Gonzalez and Lautaro Martinez (who scored the winner vs England) are all in the mix to start.",
      impact: "positive",
    },
    {
      team: "Model",
      text: "The two sub-models disagree sharply — form-based Dixon-Coles has Spain at 61%, the ELO ratings have Argentina at 46%. When they split like this the confidence is low, which is why the suggested Spain stake (0.4%) is a fraction of the bronze final's. Don't go heavy on either side.",
      impact: "neutral",
    },
    {
      team: "History",
      text: "Finals are tight: five of the last eight went to extra time, three of eight to penalties, and only about two of eight went over 2.5 goals in 90. The model's low-scoring, narrow-margin read matches the pattern.",
      impact: "neutral",
    },
    {
      team: "Model",
      text: "The win probabilities don't ingest late lineup news. If Yamal is a surprise absentee, shade toward Argentina — but as of the latest reports he's expected to play.",
      impact: "neutral",
    },
  ],
  bottomLine:
    "Check the confirmed XIs first, but as of the latest reports Yamal is expected to start. Spain to win at $2.30 is the model's pick — the edge is thin and the two sub-models disagree, so keep the stake small. If you lean Argentina, back them to lift the trophy (outright), not the 90-minute result: it's a knockout, extra time and pens are live, and our ELO model actually favours them. Honest read: this is a low-confidence final. A tight, cagey 1-1 is the single most likely outcome and there's no big edge in any one market.",
}

function TagBadge({ tag }: { tag: Pick["tag"] }) {
  const styles: Record<Pick["tag"], string> = {
    "BEST BET": "bg-emerald-500/20 text-emerald-300 border-emerald-600/40",
    "VALUE": "bg-blue-500/20 text-blue-300 border-blue-600/40",
    "CONTRARIAN": "bg-amber-500/20 text-amber-300 border-amber-600/40",
    "AVOID": "bg-rose-500/20 text-rose-300 border-rose-600/40",
  }
  return (
    <span className={`text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded border ${styles[tag]}`}>
      {tag}
    </span>
  )
}

function ImpactDot({ impact }: { impact: FactorItem["impact"] }) {
  const colors = {
    positive: "bg-emerald-400",
    negative: "bg-rose-400",
    neutral: "bg-slate-500",
  }
  return <span className={`mt-1.5 w-1.5 h-1.5 rounded-full shrink-0 ${colors[impact]}`} />
}

function PickCard({ pick }: { pick: Pick }) {
  return (
    <div className={`rounded-lg border p-3 mb-2.5 ${
      pick.tag === "BEST BET" ? "border-emerald-700/40 bg-emerald-950/20" :
      pick.tag === "AVOID" ? "border-rose-900/30 bg-rose-950/10" :
      pick.tag === "CONTRARIAN" ? "border-amber-900/30 bg-amber-950/10" :
      "border-edge bg-surface-1"
    }`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <div className="flex items-center gap-2">
          <TagBadge tag={pick.tag} />
          <span className="text-[11px] text-slate-500 font-semibold">{pick.market}</span>
        </div>
        <span className="text-[14px] font-bold font-mono tabular-nums text-slate-100 shrink-0">{pick.odds}</span>
      </div>
      <p className="text-[13px] font-bold text-slate-100 mb-1">{pick.selection}</p>
      <p className="text-[10px] text-slate-500 mb-2">{pick.confidence}</p>
      <p className="text-[11.5px] text-slate-300 leading-relaxed mb-2">{pick.why}</p>
      {pick.tag !== "AVOID" && (
        <p className="text-[10px] text-slate-400 font-mono">
          <span className="text-slate-600">Stake: </span>{pick.stake}
        </p>
      )}
    </div>
  )
}

function Block({ data }: { data: MatchGuide }) {
  return (
    <div className="rounded-xl border border-amber-500/20 bg-gradient-to-b from-amber-950/20 to-surface-2/40 p-4 mb-4">
      {/* Header */}
      <div className="mb-3">
        <h3 className="text-[14px] font-bold text-amber-300">{data.title}</h3>
        <p className="text-[10px] text-slate-500 mt-0.5">{data.kickoff} · {data.venue}</p>
      </div>

      {/* Model read summary */}
      <div className="rounded-lg bg-surface-1/60 border border-edge/60 p-2.5 mb-3">
        <p className="text-[9px] uppercase tracking-widest text-slate-600 mb-1">Model read</p>
        <p className="text-[11.5px] text-slate-300 leading-relaxed">{data.modelRead}</p>
      </div>

      {/* Injuries & factors */}
      <div className="mb-3">
        <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">Injuries & determining factors</p>
        <ul className="space-y-1.5">
          {data.factors.map((f, i) => (
            <li key={i} className="flex gap-2">
              <ImpactDot impact={f.impact} />
              <div>
                <span className={`text-[10px] font-bold uppercase tracking-wider ${
                  f.impact === "positive" ? "text-emerald-400" :
                  f.impact === "negative" ? "text-rose-400" :
                  "text-slate-500"
                }`}>{f.team}: </span>
                <span className="text-[11px] text-slate-300 leading-relaxed">{f.text}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>

      {/* Picks */}
      <div className="mb-3">
        <p className="text-[10px] uppercase tracking-widest text-slate-600 mb-2">The picks</p>
        {data.picks.map((pick, i) => (
          <PickCard key={i} pick={pick} />
        ))}
      </div>

      {/* Bottom line */}
      <div className="rounded-lg bg-amber-950/20 border border-amber-800/30 p-2.5">
        <p className="text-[9px] uppercase tracking-widest text-amber-500/70 mb-1">Bottom line</p>
        <p className="text-[11.5px] text-slate-200 leading-relaxed">{data.bottomLine}</p>
      </div>

      <p className="text-[9px] text-slate-600 mt-3 italic">
        Model numbers are the live prediction above (win probs, xG, scorelines, market-implied). Market prices where quoted are live; prices marked &ldquo;fair&rdquo; are model-derived — shop around. Injury news from team reporting as of 18 July. Historical patterns from WC 1994-2022. Not financial advice. 18+ only.
      </p>
    </div>
  )
}

export function FinalsBettingGuide({ matchId }: { matchId: string }) {
  if (matchId === "M103") return <Block data={THIRD_PLACE} />
  if (matchId === "M104") return <Block data={FINAL} />
  return null
}
