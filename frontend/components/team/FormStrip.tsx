import Link from "next/link"

interface FormGame {
  match_id: string
  opponent_code: string
  score: string
  result: "W" | "L" | "D" | null
  venue: "H" | "A"
}

const RESULT_COLORS: Record<string, string> = {
  W: "bg-emerald-600 text-white border-emerald-500/40",
  L: "bg-rose-700 text-white border-rose-600/40",
  D: "bg-slate-600 text-white border-slate-500/40",
}

// Compact left-to-right form line (oldest → newest). Each square is the
// outcome letter colored by result; tooltip shows opponent + score; click
// drops into the match detail page. Renders a soft hint when there's no
// completed match history yet.
export function FormStrip({ games, teamCode }: { games: FormGame[]; teamCode: string }) {
  if (!games.length) {
    return <p className="text-[11px] text-slate-600">Form will appear after this team has played a match.</p>
  }
  return (
    <div className="flex items-center gap-1.5">
      {games.map((g) => {
        const color = g.result ? RESULT_COLORS[g.result] : "bg-slate-800 text-slate-500 border-slate-700"
        const label = g.result ?? "?"
        return (
          <Link
            key={g.match_id}
            href={`/match/${g.match_id}?from=${encodeURIComponent("/team/" + teamCode)}`}
            title={`${g.venue === "H" ? "vs" : "at"} ${g.opponent_code.toUpperCase()} · ${g.score}`}
            className={`w-7 h-7 rounded-md border flex items-center justify-center font-mono font-bold text-[12px] hover:ring-2 hover:ring-emerald-400/40 transition-shadow ${color}`}
          >
            {label}
          </Link>
        )
      })}
    </div>
  )
}
