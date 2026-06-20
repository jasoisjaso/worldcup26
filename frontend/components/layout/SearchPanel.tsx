"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { Search, X } from "lucide-react"

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

type TeamHit = {
  code: string
  name: string
  flag_url?: string | null
  elo?: number
}

type PlayerHit = {
  id: number
  name: string
  position?: string | null
  team_name?: string | null
  photo_url?: string | null
  nation_code?: string | null
  is_wc_team?: boolean
}

type SearchResult = {
  teams: TeamHit[]
  players: PlayerHit[]
  query: string
}

const EMPTY: SearchResult = { teams: [], players: [], query: "" }

function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms)
    return () => clearTimeout(t)
  }, [value, ms])
  return v
}

type Props = { onClose: () => void }

export function SearchPanel({ onClose }: Props) {
  const router = useRouter()
  const [q, setQ] = useState("")
  const [data, setData] = useState<SearchResult>(EMPTY)
  const [loading, setLoading] = useState(false)
  const [cursor, setCursor] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const debouncedQ = useDebounced(q, 200)

  const flat: Array<{ kind: "team"; item: TeamHit } | { kind: "player"; item: PlayerHit }> = [
    ...data.teams.map((t) => ({ kind: "team" as const, item: t })),
    ...data.players.map((p) => ({ kind: "player" as const, item: p })),
  ]

  const goto = useCallback(
    (row: typeof flat[number]) => {
      const href = row.kind === "team" ? `/team/${row.item.code}` : `/player/${row.item.id}`
      onClose()
      router.push(href)
    },
    [router, onClose, flat],
  )

  // Lock body scroll + focus input + Escape to close.
  useEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = "hidden"
    const t = setTimeout(() => inputRef.current?.focus(), 10)
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose()
    }
    window.addEventListener("keydown", onKey)
    return () => {
      document.body.style.overflow = prev
      window.removeEventListener("keydown", onKey)
      clearTimeout(t)
    }
  }, [onClose])

  // Fetch on debounced input.
  useEffect(() => {
    if (debouncedQ.trim().length < 2) {
      setData(EMPTY)
      setLoading(false)
      setCursor(0)
      return
    }
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac
    setLoading(true)
    fetch(`${API_BASE}/search?q=${encodeURIComponent(debouncedQ.trim())}`, {
      signal: ac.signal,
      cache: "no-store",
    })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((json: SearchResult) => {
        setData(json)
        setCursor(0)
      })
      .catch((e) => {
        if (e?.name !== "AbortError") setData(EMPTY)
      })
      .finally(() => setLoading(false))
    return () => ac.abort()
  }, [debouncedQ])

  const onInputKey = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault()
      setCursor((c) => Math.min(flat.length - 1, c + 1))
    } else if (e.key === "ArrowUp") {
      e.preventDefault()
      setCursor((c) => Math.max(0, c - 1))
    } else if (e.key === "Enter" && flat[cursor]) {
      e.preventDefault()
      goto(flat[cursor])
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm animate-in fade-in"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Search"
    >
      <div
        className="absolute left-1/2 top-[8vh] sm:top-[12vh] -translate-x-1/2 w-[94%] max-w-xl rounded-2xl border border-edge bg-surface-1 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        style={{ marginTop: "env(safe-area-inset-top)" }}
      >
        <div className="flex items-center gap-2 px-3 py-3 border-b border-edge">
          <Search size={18} className="text-slate-500" />
          <input
            ref={inputRef}
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onInputKey}
            placeholder="Search teams or players"
            className="flex-1 bg-transparent text-[15px] text-ink placeholder:text-slate-600 outline-none"
            autoComplete="off"
            spellCheck={false}
          />
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-500 hover:text-slate-200 hover:bg-surface-2"
            aria-label="Close search"
          >
            <X size={16} />
          </button>
        </div>

        <div className="max-h-[65vh] overflow-y-auto">
          {q.trim().length < 2 ? (
            <p className="px-4 py-6 text-[12px] text-slate-500">
              Type at least 2 letters to find a team or player.
            </p>
          ) : loading && flat.length === 0 ? (
            <p className="px-4 py-6 text-[12px] text-slate-500">Searching...</p>
          ) : flat.length === 0 ? (
            <p className="px-4 py-6 text-[12px] text-slate-500">No matches for &ldquo;{q}&rdquo;.</p>
          ) : (
            <>
              {data.teams.length > 0 && (
                <div>
                  <p className="px-4 pt-3 pb-1 text-[10px] font-bold tracking-widest text-slate-600 uppercase">Teams</p>
                  {data.teams.map((t, i) => {
                    const idx = i
                    const active = cursor === idx
                    return (
                      <button
                        key={t.code}
                        onClick={() => goto({ kind: "team", item: t })}
                        onMouseEnter={() => setCursor(idx)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          active ? "bg-emerald-500/10" : "hover:bg-surface-2"
                        }`}
                      >
                        {t.flag_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={t.flag_url} alt="" width={28} height={20} className="rounded-sm shrink-0" />
                        ) : (
                          <span className="w-7 h-5 rounded-sm bg-surface-2 shrink-0" />
                        )}
                        <span className="flex-1 min-w-0">
                          <span className={`block text-[13px] font-semibold truncate ${active ? "text-emerald-300" : "text-ink"}`}>
                            {t.name}
                          </span>
                          {!!t.elo && (
                            <span className="block text-[10.5px] text-slate-500">Elo {t.elo}</span>
                          )}
                        </span>
                        <span className="text-[10px] text-slate-600 uppercase tracking-widest">Team</span>
                      </button>
                    )
                  })}
                </div>
              )}

              {data.players.length > 0 && (
                <div>
                  <p className="px-4 pt-3 pb-1 text-[10px] font-bold tracking-widest text-slate-600 uppercase">Players</p>
                  {data.players.map((p, i) => {
                    const idx = data.teams.length + i
                    const active = cursor === idx
                    return (
                      <button
                        key={p.id}
                        onClick={() => goto({ kind: "player", item: p })}
                        onMouseEnter={() => setCursor(idx)}
                        className={`w-full flex items-center gap-3 px-4 py-2.5 text-left transition-colors ${
                          active ? "bg-emerald-500/10" : "hover:bg-surface-2"
                        }`}
                      >
                        {p.photo_url ? (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img src={p.photo_url} alt="" width={28} height={28} className="rounded-full shrink-0 bg-surface-2" />
                        ) : (
                          <span className="w-7 h-7 rounded-full bg-surface-2 shrink-0" />
                        )}
                        <span className="flex-1 min-w-0">
                          <span className={`block text-[13px] font-semibold truncate ${active ? "text-emerald-300" : "text-ink"}`}>
                            {p.name}
                          </span>
                          <span className="block text-[10.5px] text-slate-500 truncate">
                            {[p.position, p.team_name].filter(Boolean).join(" · ")}
                          </span>
                        </span>
                        <span className="text-[10px] text-slate-600 uppercase tracking-widest">
                          {p.is_wc_team ? "WC" : "Player"}
                        </span>
                      </button>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>

        <div className="px-4 py-2 border-t border-edge flex items-center justify-between text-[10px] text-slate-600">
          <span>↑↓ to move · Enter to open · Esc to close</span>
          <span className="hidden sm:inline">Ctrl/Cmd K</span>
        </div>
      </div>
    </div>
  )
}
