// frontend/components/match/FinalsBettingGuide.tsx
// Strategy advice for the final two matches.
// Uses the model's actual numbers + historical finals patterns.
// Written like a punter, not a textbook.

const THIRD_PLACE = {
  title: "3rd Place: France vs England",
  tag: "The dead rubber that usually pays the best",
  lines: [
    "Third place games are loose. Nobody wants to be here. Both teams just lost a semi and couldn't care less about defending. That's exactly why the goals flow. Last 7 tournaments averaged 3.4 goals per game. Over 2.5 hit 6 of 7.",
    "But the model says Under 2.5 (59%) and the top scoreline is 1-0 (14%). That's because the model rates England at 0.71 expected goals. France at 1.62. England looked toothless against Argentina and Haaland-less Norway exposed them.",
    "The model says France win 57% and advance 75%. That's the safest single bet on the board. France @ 2.00 with a 4-point edge is a genuine play.",
    "Where the big money is: France to win AND under 2.5. Model has France 1-0 or 2-0 as the two most likely scorelines. A France win to nil at the right price covers both. Check the anytime scorer sheet for Mbappe.",
    "England at 3.80 is tempting but the model gives them 16% and only 0.71 expected goals. Don't back a team that can't score in a game nobody wants to play.",
  ],
}

const FINAL = {
  title: "Final: Spain vs Argentina",
  tag: "Two different teams. Two different bets.",
  lines: [
    "Spain are the model's pick. 44.5% win, 63% to lift the trophy. The bookies have them at 2.25 which is a 2-point edge. That's your anchor bet. Spain win or Spain to advance.",
    "Argentina are 25.5% to win in 90 but 37% to lift the trophy. The gap is penalties. If this goes to a shootout (16% chance) it's a coin flip. If you fancy Argentina, bet them to ADVANCE not to win in 90. You get the shootout insurance.",
    "Under 2.5 is 55% and that's what finals do. 1-1 is the single most likely scoreline at 14%. 1-0 is 10%. Only 2 of the last 8 finals went over 2.5 in normal time.",
    "Both teams to score is 52%. Almost a coin flip. The model's top 4 scorelines all have at least one team scoring 0 or 1. Skip BTTS.",
    "The value multi: Spain win + Under 2.5. Model has Spain 1-0 (10%) and 2-0 (9%) as the 2nd and 3rd most likely results. At combined odds of roughly 3.50 that's the biggest payout with the best model backing.",
    "api-football's model agrees Spain are favourites (45%) but thinks it's a draw (45%) way more than we do (30%). They're probably pricing in that finals go to ET. If you think it goes long, the draw at 2.95 is the contrarian play.",
  ],
}

function Block({ data }: { data: { title: string; tag: string; lines: string[] } }) {
  return (
    <div className="rounded-xl border border-amber-500/20 bg-gradient-to-b from-amber-950/20 to-surface-2/40 p-4 mb-4">
      <div className="mb-3">
        <h3 className="text-[14px] font-bold text-amber-300">{data.title}</h3>
        <p className="text-[11px] text-slate-500 italic mt-0.5">{data.tag}</p>
      </div>
      <ul className="space-y-2">
        {data.lines.map((s, i) => (
          <li key={i} className="text-[11.5px] text-slate-300 leading-relaxed flex gap-2">
            <span className="text-amber-400/60 shrink-0 mt-0.5">{"-"}</span>
            <span>{s}</span>
          </li>
        ))}
      </ul>
      <p className="text-[9px] text-slate-600 mt-3 italic">
        Model numbers from the live prediction above. Historical patterns from WC 1998-2022. Not financial advice. 18+ only.
      </p>
    </div>
  )
}

export function FinalsBettingGuide({ matchId }: { matchId: string }) {
  if (matchId === "M103") return <Block data={THIRD_PLACE} />
  if (matchId === "M104") return <Block data={FINAL} />
  return null
}
