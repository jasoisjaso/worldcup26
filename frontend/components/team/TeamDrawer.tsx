"use client"
import { useEffect, useState } from "react"
import { X, User, MapPin, Star } from "lucide-react"
import Image from "next/image"
import { KickoffTime } from "@/components/common/KickoffTime"
import type { TeamProfile, SquadPlayer } from "@/lib/types"

function spBar(value: number) {
  const pct = Math.round(((value + 0.5) / 1.0) * 100)
  const color = value > 0.1 ? "bg-emerald-500" : value < -0.1 ? "bg-red-500" : "bg-slate-500"
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-[#1a2033] rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-400 w-10 text-right tabular-nums">
        {value > 0 ? "+" : ""}{value.toFixed(2)}
      </span>
    </div>
  )
}

const POS_LABELS: Record<string, string> = {
  Goalkeeper: "GK",
  Defender: "DEF",
  Midfielder: "MID",
  Attacker: "FWD",
}

function SquadSection({ players }: { players: SquadPlayer[] }) {
  const groups: Record<string, SquadPlayer[]> = {}
  for (const p of players) {
    const pos = p.position || "Unknown"
    if (!groups[pos]) groups[pos] = []
    groups[pos].push(p)
  }
  const order = ["Goalkeeper", "Defender", "Midfielder", "Attacker"]
  const sorted = order.filter((k) => groups[k]).concat(Object.keys(groups).filter((k) => !order.includes(k)))

  return (
    <div className="space-y-3">
      {sorted.map((pos) => (
        <div key={pos}>
          <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-1.5">
            {POS_LABELS[pos] ?? pos}
          </p>
          <div className="flex flex-wrap gap-1">
            {groups[pos].map((p, i) => (
              <span
                key={p.id ?? i}
                className="text-[11px] text-slate-300 bg-[#0c1220] border border-[#1a2033] rounded px-2 py-0.5"
              >
                {p.number ? <span className="text-slate-600 mr-1">{p.number}</span> : null}
                {p.name}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

interface Props {
  code: string
  onClose: () => void
}

export function TeamDrawer({ code, onClose }: Props) {
  const [profile, setProfile] = useState<TeamProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setProfile(null)
    setError(false)
    // Use Next.js proxy route — avoids browser calling backend directly (which would
    // fail because NEXT_PUBLIC_API_URL=http://localhost:8000 isn't reachable from
    // the user's browser when accessing the site remotely).
    fetch(`/api/proxy/teams/${code}`)
      .then((r) => {
        if (!r.ok) throw new Error(`${r.status}`)
        return r.json()
      })
      .then((d) => {
        if (d.error) throw new Error(d.error)
        setProfile(d)
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false))
  }, [code])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [onClose])

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
        onClick={onClose}
      />
      <div className="fixed right-0 top-0 h-full w-full max-w-sm bg-[#080d17] border-l border-[#1a2033] z-50 overflow-y-auto">
        <div className="flex items-center justify-between px-4 py-3 border-b border-[#1a2033] sticky top-0 bg-[#080d17] z-10">
          {profile ? (
            <div className="flex items-center gap-2.5">
              {profile.flag_url && (
                <Image src={profile.flag_url} alt="" width={28} height={20} className="rounded-sm object-cover" unoptimized />
              )}
              <div>
                <h2 className="text-[15px] font-bold text-white leading-tight">{profile.name}</h2>
                <p className="text-[10px] text-slate-500">Group Stage</p>
              </div>
            </div>
          ) : (
            <div className="h-6 w-32 bg-[#1a2033] rounded animate-pulse" />
          )}
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors p-1">
            <X size={18} />
          </button>
        </div>

        {loading && (
          <div className="px-4 py-8 space-y-3">
            {[1,2,3].map(i => <div key={i} className="h-16 bg-[#0c1220] rounded-xl animate-pulse" />)}
          </div>
        )}

        {error && !loading && (
          <div className="px-4 py-8 text-center text-slate-500 text-[12px]">
            Could not load team data.
          </div>
        )}

        {!loading && !error && profile && (
          <div className="px-4 py-4 space-y-5">
            <div className="grid grid-cols-2 gap-2">
              <div className="bg-[#0c1220] border border-[#1a2033] rounded-xl px-3 py-2.5">
                <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-1">ELO Rating</p>
                <p className="text-[20px] font-extrabold text-white leading-none">{Math.round(profile.elo)}</p>
              </div>
              <div className="bg-[#0c1220] border border-[#1a2033] rounded-xl px-3 py-2.5">
                <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest mb-1">FIFA Rank</p>
                <p className="text-[20px] font-extrabold text-white leading-none">
                  {profile.fifa_ranking ? `#${profile.fifa_ranking}` : "N/A"}
                </p>
              </div>
            </div>

            {profile.manager && (
              <div className="flex items-center gap-2 bg-[#0c1220] border border-[#1a2033] rounded-xl px-3 py-2.5">
                <User size={13} className="text-slate-500 shrink-0" />
                <div>
                  <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Manager</p>
                  <p className="text-[13px] font-semibold text-slate-200">{profile.manager}</p>
                </div>
              </div>
            )}

            <div className="bg-[#0c1220] border border-[#1a2033] rounded-xl px-3 py-2.5">
              <div className="flex items-center gap-1.5 mb-3">
                <Star size={11} className="text-slate-500" />
                <p className="text-[9px] font-bold text-slate-600 uppercase tracking-widest">Set Piece Index</p>
              </div>
              <div className="space-y-2">
                <div>
                  <p className="text-[10px] text-slate-500 mb-1">Attack threat</p>
                  {spBar(profile.set_piece_attack)}
                </div>
                <div>
                  <p className="text-[10px] text-slate-500 mb-1">Defensive solidity</p>
                  {spBar(profile.set_piece_defense)}
                </div>
              </div>
            </div>

            {profile.upcoming_fixtures.length > 0 && (
              <div>
                <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
                  <MapPin size={10} className="inline mr-1" />
                  Upcoming Fixtures
                </p>
                <div className="space-y-1.5">
                  {profile.upcoming_fixtures.map((f) => (
                    <div key={f.match_id} className="bg-[#0c1220] border border-[#1a2033] rounded-lg px-3 py-2 flex items-center justify-between">
                      <div className="flex items-center gap-2 min-w-0">
                        {f.opponent_flag && (
                          <Image src={f.opponent_flag} alt="" width={18} height={13} className="rounded-sm object-cover shrink-0" unoptimized />
                        )}
                        <div className="min-w-0">
                          <p className="text-[12px] font-semibold text-slate-200 truncate">
                            {f.is_home ? "vs" : "@"} {f.opponent}
                          </p>
                          <p className="text-[10px] text-slate-500">MD{f.matchday} · Group {f.group}</p>
                        </div>
                      </div>
                      {f.kickoff && (
                        <p className="text-[10px] text-slate-500 shrink-0 ml-2">
                          <KickoffTime iso={f.kickoff} />
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {profile.squad.length > 0 && (
              <div>
                <p className="text-[10px] font-bold text-slate-600 uppercase tracking-widest mb-2">
                  Squad ({profile.squad.length})
                </p>
                <SquadSection players={profile.squad} />
              </div>
            )}

            {profile.squad.length === 0 && (
              <p className="text-[11px] text-slate-600 text-center py-2">
                Squad data loads once API key is active.
              </p>
            )}
          </div>
        )}
      </div>
    </>
  )
}
