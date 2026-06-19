import type { Metadata } from "next"
import { TopBar } from "@/components/layout/TopBar"
import { BracketTree } from "@/components/bracket/BracketTree"
import { BracketLive } from "@/components/bracket/BracketLive"
import { api } from "@/lib/api"

export const metadata: Metadata = {
  title: "World Cup 2026 Bracket: Projected & Live Knockout Tree",
  description:
    "The 2026 FIFA World Cup knockout bracket: projected from 20,000 simulations before groups finish, then locked in with real teams as each group completes.",
  alternates: { canonical: "https://wc26.tinjak.com/bracket" },
}

export const dynamic = "force-dynamic"

export default async function BracketPage() {
  let projection
  let liveBracket
  try {
    ;[projection, liveBracket] = await Promise.all([
      api.tournament(),
      api.bracketLive(),
    ])
  } catch {
    projection = null
    liveBracket = null
  }

  const hasLive = liveBracket && liveBracket.groups_done > 0

  return (
    <>
      <TopBar
        title="Knockout Bracket"
        subtitle={
          hasLive
            ? `${liveBracket.groups_done}/12 groups locked in. Real matchups below.`
            : "Projected bracket from 20,000 simulations. Locks in as groups complete."
        }
      />
      <div className="max-w-5xl mx-auto px-3 sm:px-5 py-5">
        {/* Live bracket: shown when groups have finished */}
        {hasLive && liveBracket.bracket?.rounds?.[0]?.matches?.some((m: any) => m.locked) && (
          <div className="mb-8">
            <BracketLive data={liveBracket} />
          </div>
        )}

        {/* Projected bracket: always shown, but labeled differently when live exists */}
        {projection?.bracket && projection.teams.length > 0 ? (
          <div>
            {hasLive && (
              <p className="text-[11px] font-bold uppercase tracking-[0.15em] text-amber-400/80 mb-3">
                Projected (simulation). Remaining slots filled by the model.
              </p>
            )}
            <BracketTree projection={projection} />
          </div>
        ) : (
          <p className="text-slate-500 text-sm py-16 text-center">
            The bracket is warming up. Refresh in a moment.
          </p>
        )}
      </div>
    </>
  )
}
