"use client"
import Link from "next/link"
import { useState } from "react"

// Per-player row for the team page squad grid. Photo + name + position + age,
// with the season scoreline (goals/assists) pinned right when we have stats.
// Click goes to the player detail page. Photo URLs sometimes 404 (CDN drift) —
// onError swaps in a neutral avatar so the row never collapses.

interface Player {
  player_id: number
  name: string
  position: string
  age: number | null
  photo_url: string | null
  stats: { appearances: number; goals: number; assists: number; minutes: number } | null
  per90?: {
    season: string | null; minutes: number | null
    goals_per90: number | null; assists_per90: number | null
    shots_per90: number | null; key_passes_per90: number | null
    pass_accuracy_pct: number | null; rating: number | null
  } | null
}

export function PlayerCard({ player: p, teamCode }: { player: Player; teamCode: string }) {
  const [photoFailed, setPhotoFailed] = useState(false)
  const hasStats = p.stats && p.stats.appearances > 0
  const showPhoto = p.photo_url && !photoFailed
  // Per-90 club-season output (Rising Transfers dataset). Shown as the headline
  // numbers when we have no WC stats yet, and as a club-form subline otherwise —
  // so a squad reads with real recent output instead of "No stats yet".
  const g90 = p.per90?.goals_per90
  const a90 = p.per90?.assists_per90
  const rating = p.per90?.rating
  const hasPer90 = p.per90 != null && (g90 != null || a90 != null)

  return (
    <Link
      href={`/player/${p.player_id}?from=${encodeURIComponent("/team/" + teamCode)}`}
      className="group flex items-center gap-3 rounded-xl border border-edge bg-surface-2 shadow-e1 px-3 py-2.5 hover:border-emerald-500/40 transition-colors"
    >
      {showPhoto ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={p.photo_url!}
          alt={p.name}
          onError={() => setPhotoFailed(true)}
          className="w-11 h-11 rounded-full object-cover ring-1 ring-white/10 shrink-0 bg-slate-800"
        />
      ) : (
        <div className="w-11 h-11 rounded-full bg-slate-800 ring-1 ring-white/10 shrink-0 flex items-center justify-center text-slate-500 text-[12px] font-bold">
          {p.name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase()}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-bold text-white truncate group-hover:text-emerald-300 transition-colors">{p.name}</p>
        <p className="text-[10px] text-slate-500">
          {p.position}{p.age ? ` · ${p.age}` : ""}
        </p>
        {/* Club-season per-90 subline — only when we ALSO show WC stats on the
            right, so the two don't duplicate. */}
        {hasStats && hasPer90 && (
          <p className="text-[9px] text-slate-600 mt-0.5 tabular-nums">
            {g90 != null && <>{g90.toFixed(2)} G/90</>}
            {a90 != null && <> · {a90.toFixed(2)} A/90</>}
            {rating != null && <> · {rating.toFixed(2)} rating</>}
            <span className="text-slate-700"> · {p.per90?.season ?? "club"}</span>
          </p>
        )}
      </div>
      {hasStats ? (
        <div className="flex items-center gap-2.5 shrink-0 text-right">
          <div>
            <p className="font-mono text-[14px] font-black text-amber-400 tabular-nums leading-none">{p.stats!.goals}</p>
            <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">Goals</p>
          </div>
          {p.stats!.assists > 0 && (
            <div>
              <p className="font-mono text-[14px] font-bold text-emerald-400 tabular-nums leading-none">{p.stats!.assists}</p>
              <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">Asts</p>
            </div>
          )}
        </div>
      ) : hasPer90 ? (
        // No WC stats yet → show the per-90 club-season output as the headline
        // numbers. This is the fix for "No stats yet" on 87% of squad players.
        <div className="flex items-center gap-2.5 shrink-0 text-right" title={`${p.per90?.season ?? "club"} per-90`}>
          {g90 != null && (
            <div>
              <p className="font-mono text-[13px] font-black text-amber-400 tabular-nums leading-none">{g90.toFixed(2)}</p>
              <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">G/90</p>
            </div>
          )}
          {a90 != null && a90 > 0 && (
            <div>
              <p className="font-mono text-[13px] font-bold text-emerald-400 tabular-nums leading-none">{a90.toFixed(2)}</p>
              <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">A/90</p>
            </div>
          )}
          {rating != null && (
            <div>
              <p className="font-mono text-[13px] font-bold text-slate-200 tabular-nums leading-none">{rating.toFixed(1)}</p>
              <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">Rtg</p>
            </div>
          )}
        </div>
      ) : (
        <span className="text-[9px] text-slate-700 shrink-0 uppercase tracking-wider">No stats yet</span>
      )}
    </Link>
  )
}
