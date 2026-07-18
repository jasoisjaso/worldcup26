// frontend/components/match/FinalsBettingGuide.tsx
// Clear, actionable betting guide for the final two matches of the tournament.
// Tells the user EXACTLY what to bet, at what price, why, and what injuries
// and factors are driving the call. Updated with real team news as of July 18.

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
    "France 57% · Draw 28% · England 16%. xG: France 1.62, England 0.71. Top scorelines: 1-0 (14%), 2-0 (13%), 1-1 (13%). Under 2.5 at 59%.",
  picks: [
    {
      market: "Match Result",
      selection: "France to win",
      odds: "$2.00",
      confidence: "57% model prob · 7-point edge vs bookies",
      stake: "3.4% of bankroll ($34 on $1,000)",
      why: "Safest single bet on the board. France are rated 57% by the model, bookies imply 50%. That 7-point gap is the biggest edge in either final-weekend match. England scored 0.71 xG — they can't score. France have Mbappe chasing the Golden Boot (8 goals, tied with Messi). He's motivated.",
      tag: "BEST BET",
    },
    {
      market: "Match Result + Total Goals",
      selection: "France win AND Under 2.5",
      odds: "~$3.50 combined",
      confidence: "France 1-0 (14%) or 2-0 (13%) are the top 2 scorelines",
      stake: "1-2 units (higher risk, bigger payout)",
      why: "The model's top two scorelines are both France wins to nil. A France win to nil at the right price covers both. France clean sheet is 49%. England's attack is toothless (0.71 xG, Kane isolated, no service). If you can get France win to nil as a single at ~$2.60, that's cleaner than the multi.",
      tag: "VALUE",
    },
    {
      market: "Anytime Goalscorer",
      selection: "Mbappe to score anytime",
      odds: "$1.72",
      confidence: "58% model prob",
      stake: "2-3 units",
      why: "Mbappe has 8 goals, tied with Messi for the Golden Boot. This is his last game of the tournament. He's going to play every minute and take every chance. 58% at $1.72 is fair value. England's reshuffled defence without James and with a fatigued Rice is there to be exposed.",
      tag: "VALUE",
    },
    {
      market: "Total Goals",
      selection: "Over 2.5",
      odds: "~$2.43 fair",
      confidence: "Model says Under 2.5 (59%) — but see factors below",
      stake: "0 — do not bet",
      why: "The model says Under, but Saliba is OUT for France and both teams are rotating heavily in a dead rubber. Third place games historically average 3.4 goals (Over hit 6 of last 7). The model hasn't factored in Saliba's absence or the rotation. This is the one spot where the model is likely wrong. Skip it either way — too much uncertainty to bet either direction.",
      tag: "AVOID",
    },
    {
      market: "Match Result",
      selection: "England to win",
      odds: "$3.80",
      confidence: "16% model prob · 0.71 xG",
      stake: "0",
      why: "England have 16% win probability and 0.71 expected goals. They lost Reece James to injury, Henderson is hospitalized after arm surgery, Declan Rice is battling fatigue/illness/calf/hamstring issues. Tuchel is rotating heavily. Don't back a banged-up team that can't score in a game nobody wants to play.",
      tag: "AVOID",
    },
  ],
  factors: [
    {
      team: "France",
      text: "William Saliba OUT — back injury ('my back is gone' walking off vs Spain). Pre-existing issue, likely surgery. France's best centre-back gone. Maxence Lacroix likely to step in.",
      impact: "negative",
    },
    {
      team: "France",
      text: "Brice Samba (backup GK) also out. Deschamps rotating heavily — his last game in charge. Cherki, Kone, Zaire-Emery, Doue, Barcola all likely to start. Konate for Upamecano, Theo Hernandez for Digne.",
      impact: "neutral",
    },
    {
      team: "France",
      text: "Mbappe (8 goals) chasing Golden Boot — fully motivated to play and score. This is the one constant amid the rotation.",
      impact: "positive",
    },
    {
      team: "England",
      text: "Reece James DOUBT — went off injured vs Argentina in the semi. May be replaced by Djed Spence or Jarell Quansah (back from suspension).",
      impact: "negative",
    },
    {
      team: "England",
      text: "Jordan Henderson OUT — freak arm injury celebrating the Mexico win, required surgery, hospitalised. Gone for the tournament.",
      impact: "negative",
    },
    {
      team: "England",
      text: "Declan Rice struggling — fatigue, illness, calf issue, neural pain in hamstring/lower back. Subbed at half-time vs Norway, subbed again vs Argentina. Could be rested. Kobbie Mainoo (0 minutes all tournament) may get his chance.",
      impact: "negative",
    },
    {
      team: "England",
      text: "Kane and Bellingham (6 goals each) want to start to chase the Golden Boot. But Tuchel is expected to make 'significant changes' — rotation is the story for England.",
      impact: "neutral",
    },
    {
      team: "Model",
      text: "The model page says 'No known absences' for both teams. That's STALE — Saliba, Henderson, James, and Rice issues are all unaccounted for. Treat the model's Under 2.5 call with extra caution given the defensive changes.",
      impact: "neutral",
    },
  ],
  bottomLine:
    "Back France to win at $2.00. That's the clearest edge on the board. If you want a bigger payout, France win to nil or France win + Under 2.5 covers the model's top scorelines (1-0, 2-0). Mbappe anytime at $1.72 is the secondary play — Golden Boot motivation in his last game. Avoid the Over/Under market entirely — the model hasn't factored in the injuries and third-place games are historically wild.",
}

const FINAL: MatchGuide = {
  title: "Final: Spain vs Argentina",
  kickoff: "Sun 19 July · 8pm BST",
  venue: "MetLife Stadium, East Rutherford NJ",
  modelRead:
    "Spain 44% · Draw 30% · Argentina 26%. xG: Spain 1.49, Argentina 1.04. Top scorelines: 1-1 (14%), 1-0 (10%), 0-0 (10%). Under 2.5 at 54%. WARNING: Two model views disagree — Form-based (DC) says Spain 61%, ELO ratings say Argentina 46%. Lower confidence.",
  picks: [
    {
      market: "To Lift the Trophy",
      selection: "Spain to win the World Cup",
      odds: "$2.30 (to win in 90) · ~$1.55 to advance",
      confidence: "44% in 90 · 63% to advance · Model favourite",
      stake: "0.4% of bankroll ($4 on $1,000) — model is less confident here",
      why: "Spain are the model's pick but the edge is thin (2 points). The two internal models disagree — form says Spain dominant (61%), ELO ratings say Argentina (46%). That disagreement means lower confidence. Spain beat France 2-0 in the semi and have a clean bill of health. If Yamal plays, this is the anchor bet. Check the lineups.",
      tag: "BEST BET",
    },
    {
      market: "To Advance (not to win in 90)",
      selection: "Argentina to advance",
      odds: "~$2.70",
      confidence: "37% to lift the trophy · 16% chance of penalties",
      stake: "1-2 units if you fancy Argentina",
      why: "If you're backing Argentina, bet them to ADVANCE, not to win in 90. Argentina are only 26% to win in normal time but 37% to lift the trophy. The gap is penalties — 16% chance of a shootout, and Argentina's ELO rating actually favours them (46% vs Spain's 25%). You get the extra-time and shootout insurance. Argentina have no injuries, full squad, and their subs (De Paul, N. Gonzalez, Lautaro Martinez) changed the game vs England.",
      tag: "CONTRARIAN",
    },
    {
      market: "Total Goals",
      selection: "Under 2.5",
      odds: "~$1.85 fair",
      confidence: "54% model prob · consistent with finals history",
      stake: "1-2 units",
      why: "Finals are tight. 1-1 is the single most likely scoreline (14%). Only 2 of the last 8 World Cup finals went over 2.5 in normal time. 5 of the last 8 went to extra time. The model says 54% Under and that aligns with history. Both teams defend well. This is the one market where the model and history agree clearly.",
      tag: "VALUE",
    },
    {
      market: "Match Result + Total Goals",
      selection: "Spain win AND Under 2.5",
      odds: "~$3.50 combined",
      confidence: "Spain 1-0 (10%) and 2-0 (9%) are 2nd/3rd most likely",
      stake: "0.5-1 unit (higher risk)",
      why: "The model's top scorelines after 1-1 are Spain 1-0 and Spain 2-0. If you believe Spain win it in 90 without a shootout, this multi covers the most likely clean-sheet results. But note: the draw at $2.95 is almost as likely as Spain winning (30% vs 44%), so this bet loses if it goes to pens.",
      tag: "VALUE",
    },
    {
      market: "Match Result",
      selection: "Draw (after 90 minutes)",
      odds: "$2.95",
      confidence: "30% model prob · 5 of last 8 finals went to ET",
      stake: "1 unit if you think it goes long",
      why: "The contrarian play. The draw is 30% in the model and api-football's model actually has the draw at 45%. 5 of the last 8 World Cup finals went to extra time. If you think this goes to pens (16% chance), the draw in 90 is the bet. Spain's top scoreline is 1-1 (14%) — a tight, cagey final is the historical pattern.",
      tag: "CONTRARIAN",
    },
    {
      market: "Both Teams to Score",
      selection: "BTTS — No",
      odds: "~$1.73 fair",
      confidence: "58% model prob (No) · 42% Yes",
      stake: "1 unit",
      why: "The model's top 4 scorelines all have at least one team scoring 0 or 1. 0-0 is 10%, 1-0 is 10%, 1-1 is 14%, 2-0 is 9%. Finals are cagey. Spain kept a clean sheet vs France in the semi. Argentina conceded 1 vs England but scored 2 late. If you're already on Under 2.5, BTTS No is the natural companion — both bets win on a 1-0 or 2-0.",
      tag: "VALUE",
    },
  ],
  factors: [
    {
      team: "Spain",
      text: "Lamine Yamal DOUBT — missed training before the final, spotted with strapping on his left thigh. Unclear if he'll be fit. THIS IS THE SWING FACTOR. Yamal is Spain's most dangerous attacker (0.63 G/90, 0.43 A/90). If he's out, Spain's attacking threat drops significantly and Argentina become much more appealing.",
      impact: "negative",
    },
    {
      team: "Spain",
      text: "Otherwise clean bill of health. Beat France 2-0 in the semi. Nico Williams pushing for a start. Pedri dropped last two games (Rodri and Fabian Ruiz impressing). Came through unscathed.",
      impact: "positive",
    },
    {
      team: "Argentina",
      text: "No injuries reported. Full squad available. Messi (8 goals, tied with Mbappe for Golden Boot) gets his last World Cup final.",
      impact: "positive",
    },
    {
      team: "Argentina",
      text: "Subs changed the semi vs England — De Paul, N. Gonzalez, and Lautaro Martinez (who scored the winner) all could start. Scaloni has tactical flexibility off the bench.",
      impact: "positive",
    },
    {
      team: "Model",
      text: "Two internal models DISAGREE. Form-based Dixon-Coles says Spain 61%, ELO ratings say Argentina 46%. When the two views disagree, the model's confidence is lower. The 0.4% stake suggestion (vs 3.4% for France-England) reflects this. Don't go heavy on either side.",
      impact: "neutral",
    },
    {
      team: "History",
      text: "Only 2 teams have ever won back-to-back World Cups (Italy 1934/38, Brazil 1958/62). Argentina are chasing history. Finals are tight — 5 of last 8 went to extra time, 3 of 8 went to penalties. Only 2 of 8 went over 2.5 goals in normal time.",
      impact: "neutral",
    },
    {
      team: "Model",
      text: "The model page says 'No known absences' for both teams. The Yamal injury doubt is NOT reflected in the model's numbers. If Yamal is ruled out, Spain's 44% win probability is too high — lean Argentina to advance instead.",
      impact: "neutral",
    },
  ],
  bottomLine:
    "Check the lineups before you bet. If Yamal plays: Spain to win @ $2.30 (thin edge, small stake) or Spain win + Under 2.5 for a bigger payout. If Yamal is out: switch to Argentina to advance @ ~$2.70 — you get penalty shootout insurance and the ELO model already favours Argentina. Either way, Under 2.5 is the clearest market — finals are cagey, 1-1 is the top scoreline, and history agrees with the model. Don't go heavy — the two internal models disagree, so the confidence is lower than the 3rd place match.",
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
        Model numbers from the live prediction above. Injury news from team press conferences and training reports as of July 18. Historical patterns from WC 1998-2022. Not financial advice. 18+ only.
      </p>
    </div>
  )
}

export function FinalsBettingGuide({ matchId }: { matchId: string }) {
  if (matchId === "M103") return <Block data={THIRD_PLACE} />
  if (matchId === "M104") return <Block data={FINAL} />
  return null
}
