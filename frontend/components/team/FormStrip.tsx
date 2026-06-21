import Link from "next/link"
import { Flag } from "@/components/common/Flag"

interface FormGame {
  match_id: string
  opponent_code: string
  // Optional because some legacy callers don't pass it — falls back to the code uppercased.
  opponent_name?: string
  score: string
  result: "W" | "L" | "D" | null
  venue: "H" | "A"
  kickoff?: string | null
}

const RESULT_COLORS: Record<string, string> = {
  W: "bg-emerald-600 text-white border-emerald-500/40",
  L: "bg-rose-700 text-white border-rose-600/40",
  D: "bg-slate-600 text-white border-slate-500/40",
}

function fmtShortDate(iso?: string | null) {
  if (!iso) return ""
  try {
    const d = new Date(iso)
    return d.toLocaleDateString("en-AU", { month: "short", day: "numeric" })
  } catch {
    return iso.slice(5, 10)
  }
}

// Vertical results list — one row per match with: result chip, venue badge,
// opponent flag + name, score, and short date. Mobile-first; opponent info
// is the whole point ("I only see form not who they versed", 2026-06-21).
// Each row is a Link into the match detail page.
//
// Above the list we ALSO keep a compact chip strip — old W/L/D glance at a
// glance — so the dense info doesn't lose the at-a-glance pattern. The strip
// uses the same hover ring so it reads as a navigation row, not decoration.
export function FormStrip({ games, teamCode }: { games: FormGame[]; teamCode: string }) {
  if (!games.length) {
    return <p className="text-[11px] text-slate-600">Form will appear after this team has played a match.</p>
  }

  return (
    <div className="space-y-3">
      {/* Compact chip strip — quick at-a-glance, hover for full row index below. */}
      <div className="flex items-center gap-1.5">
        {games.map((g) => {
          const color = g.result ? RESULT_COLORS[g.result] : "bg-slate-800 text-slate-500 border-slate-700"
          return (
            <Link
              key={`chip-${g.match_id}`}
              href={`/match/${g.match_id}?from=${encodeURIComponent("/team/" + teamCode)}`}
              title={`${g.venue === "H" ? "vs" : "at"} ${(g.opponent_name || g.opponent_code).toUpperCase()} · ${g.score}`}
              className={`w-7 h-7 rounded-md border flex items-center justify-center font-mono font-bold text-[12px] hover:ring-2 hover:ring-emerald-400/40 transition-shadow ${color}`}
            >
              {g.result ?? "?"}
            </Link>
          )
        })}
      </div>

      {/* Full result rows — opponent flag + name + score + date. */}
      <div className="divide-y divide-edge border border-edge rounded-lg overflow-hidden bg-surface-2">
        {games.map((g) => {
          const chipClass = g.result ? RESULT_COLORS[g.result] : "bg-slate-800 text-slate-500 border-slate-700"
          const oppName = g.opponent_name || g.opponent_code.toUpperCase()
          return (
            <Link
              key={`row-${g.match_id}`}
              href={`/match/${g.match_id}?from=${encodeURIComponent("/team/" + teamCode)}`}
              className="flex items-center gap-2 px-2.5 py-2 hover:bg-surface-3/60 transition-colors"
            >
              <span className={`w-6 h-6 shrink-0 rounded text-[10px] font-bold flex items-center justify-center border ${chipClass}`}>
                {g.result ?? "?"}
              </span>
              <span className="text-[10px] text-slate-600 uppercase tracking-wider w-3 shrink-0">
                {g.venue}
              </span>
              <Flag code={g.opponent_code} name={oppName} size="sm" />
              <span className="text-[12.5px] text-slate-200 flex-1 truncate">
                {oppName}
              </span>
              <span className="text-[12.5px] font-mono tabular-nums text-slate-100 shrink-0">
                {g.score}
              </span>
              {/* Date is the user's anchor — they asked for it to show on
                  mobile (2026-06-21 "I see the matches but no date"). The
                  earlier hidden sm:inline rule was overprotective. */}
              {g.kickoff && (
                <span className="text-[10px] font-mono tabular-nums text-slate-600 shrink-0">
                  {fmtShortDate(g.kickoff)}
                </span>
              )}
            </Link>
          )
        })}
      </div>
    </div>
  )
}
