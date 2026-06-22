import Link from "next/link"
import type { KeyPlayer } from "@/lib/types"

interface Props {
  home: KeyPlayer[]
  away: KeyPlayer[]
  homeName: string
  awayName: string
  attribution?: string
}

export function KeyPlayersToWatch({ home, away, homeName, awayName, attribution }: Props) {
  if (home.length === 0 && away.length === 0) return null
  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 sm:p-5">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-3">
        Key players to watch
      </p>
      <div className="grid sm:grid-cols-2 gap-4">
        <Side name={homeName} players={home} accent="text-emerald-400" />
        <Side name={awayName} players={away} accent="text-orange-400" />
      </div>
      {attribution && (
        <p className="text-[9px] text-slate-700 mt-3">{attribution}</p>
      )}
    </div>
  )
}

function Side({ name, players, accent }: { name: string; players: KeyPlayer[]; accent: string }) {
  return (
    <div>
      <p className={`text-[11px] font-semibold mb-2 ${accent}`}>{name}</p>
      {players.length === 0 ? (
        <p className="text-[10px] text-slate-700">No per-90 data for this squad yet.</p>
      ) : (
        <ul className="space-y-1.5">
          {players.map((p) => (
            <PlayerRow key={p.player_id ?? p.name} p={p} />
          ))}
        </ul>
      )}
    </div>
  )
}

function PlayerRow({ p }: { p: KeyPlayer }) {
  const g90 = p.goals_per90 ?? 0
  const a90 = p.assists_per90 ?? 0
  const inner = (
    <div className="flex items-center gap-2.5 rounded-lg border border-edge bg-surface-3/40 px-2.5 py-2 hover:border-emerald-500/40 transition-colors">
      <Avatar name={p.name} photoUrl={p.photo_url} />
      <div className="min-w-0 flex-1">
        <p className="text-[12px] font-semibold text-slate-100 truncate">{p.name}</p>
        <p className="text-[9px] text-slate-600 truncate">
          {p.position}
          {p.season ? ` · ${p.season}` : ""}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0 text-right tabular-nums">
        {g90 > 0 && (
          <div>
            <p className="text-[12px] font-bold text-amber-400 leading-none">{g90.toFixed(2)}</p>
            <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">G/90</p>
          </div>
        )}
        {a90 > 0 && (
          <div>
            <p className="text-[12px] font-bold text-emerald-400 leading-none">{a90.toFixed(2)}</p>
            <p className="text-[8px] text-slate-600 uppercase tracking-wider mt-0.5">A/90</p>
          </div>
        )}
      </div>
    </div>
  )
  if (p.player_id) {
    return (
      <li>
        <Link href={`/player/${p.player_id}`} className="block group">
          {inner}
        </Link>
      </li>
    )
  }
  return <li>{inner}</li>
}

function Avatar({ name, photoUrl }: { name: string; photoUrl: string | null }) {
  const initials = name
    .split(" ")
    .map((s) => s[0])
    .join("")
    .slice(0, 2)
    .toUpperCase()
  if (photoUrl) {
    // eslint-disable-next-line @next/next/no-img-element
    return (
      <img
        src={photoUrl}
        alt=""
        className="w-9 h-9 rounded-full object-cover ring-1 ring-white/10 shrink-0 bg-slate-800"
      />
    )
  }
  return (
    <div className="w-9 h-9 rounded-full bg-slate-800 ring-1 ring-white/10 shrink-0 flex items-center justify-center text-slate-500 text-[10px] font-bold">
      {initials}
    </div>
  )
}
