// frontend/components/match/FinalsBettingGuide.tsx
// Static strategy advice for the final two matches of the tournament.
// Renders only on M103 (3rd place) and M104 (Final).
// Data sourced from WC 1998-2022 historical patterns.

const THIRD_PLACE_CONTENT = {
  title: "3rd Place Playoff — how to bet it",
  patterns: [
    { label: "Avg goals", value: "3.4 per game" },
    { label: "Over 2.5 hits", value: "~85%" },
    { label: "BTTS yes", value: "~80%" },
    { label: "Common score", value: "2-1" },
    { label: "Blowouts", value: "None in last 4" },
  ],
  strategy: [
    "Nobody remembers 3rd place — both teams play loose. Defenders switch off, tactical fear disappears, goals flow.",
    "Over 2.5 + BTTS yes is the core structure. These are the highest-hit-rate markets in this fixture historically.",
    "Watch fatigue: if one team played 120 min in their semi and the other won in 90, the rested team has a real edge.",
    "Avoid 1X2 — the favourite wins ~70% but at short odds. The value is in the goals markets.",
  ],
}

const FINAL_CONTENT = {
  title: "The Final — how to bet it",
  patterns: [
    { label: "Avg goals", value: "1.9 per game" },
    { label: "Under 2.5 hits", value: "~65%" },
    { label: "Draw at HT", value: "~70%" },
    { label: "Went to ET", value: "5 of last 8" },
    { label: "Went to pens", value: "3 of last 8" },
  ],
  strategy: [
    "Finals are nervous and low-scoring. Loss aversion dominates — both teams play not to lose. The first goal is everything.",
    "Under 2.5 goals is the structural play. Only 2 of the last 8 finals had 3+ goals in normal time.",
    "Draw at half-time hits ~70%. The game opens up after the break.",
    "To Lift Trophy (not 1X2): this market prices in penalty shootouts. If you think it goes to pens, bet the trophy market.",
    "Anytime scorer on a set-piece target — finals are decided by dead balls. The big striker is tightly marked; the centre-back at big odds is value.",
  ],
}

export function FinalsBettingGuide({ matchId }: { matchId: string }) {
  const content = matchId === "M103" ? THIRD_PLACE_CONTENT
    : matchId === "M104" ? FINAL_CONTENT
    : null
  if (!content) return null

  return (
    <div className="rounded-xl border border-amber-500/20 bg-gradient-to-b from-amber-950/20 to-surface-2/40 p-4 mb-4">
      <h3 className="text-[14px] font-bold text-amber-300 mb-3">{content.title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 mb-3">
        {content.patterns.map((p) => (
          <div key={p.label} className="rounded-lg bg-surface-3/60 px-2.5 py-2">
            <p className="text-[9px] uppercase tracking-wider text-slate-500">{p.label}</p>
            <p className="text-[11px] font-bold text-slate-200 mt-0.5">{p.value}</p>
          </div>
        ))}
      </div>
      <ul className="space-y-1.5">
        {content.strategy.map((s, i) => (
          <li key={i} className="text-[11px] text-slate-400 leading-snug flex gap-1.5">
            <span className="text-amber-400/60 shrink-0">{"->"}</span>
            <span>{s}</span>
          </li>
        ))}
      </ul>
      <p className="text-[9px] text-slate-600 mt-2 italic">
        Historical patterns from WC 1998-2022. Not a guarantee — use alongside the model read above.
      </p>
    </div>
  )
}
