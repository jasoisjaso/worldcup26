"use client"
/**
 * Live in-play win-probability swing chart.
 *
 * Hand-rolled SVG (matches the project's existing viz/* convention — no chart library).
 * Connects to `/api/live/match/<id>/stream` via EventSource. Renders three smoothed lines
 * (home / draw / away) across the elapsed minute axis, annotated with the live score
 * and recent event labels (goals, red cards).
 *
 * Closes cleanly when the match ends or the user navigates away.
 */
import { useEffect, useMemo, useRef, useState } from "react"

interface Tick {
  id: number
  elapsed_min: number
  p_home: number
  p_draw: number
  p_away: number
  home_score?: number | null
  away_score?: number | null
  event_label?: string | null
}

interface LiveStateSnap {
  match_id: string
  status?: string | null
  elapsed_min?: number | null
  home_score?: number | null
  away_score?: number | null
  home_xg?: number | null
  away_xg?: number | null
  home_possession?: number | null
  away_possession?: number | null
  home_shots?: number | null
  away_shots?: number | null
  home_shots_on_target?: number | null
  away_shots_on_target?: number | null
}

interface InitialPayload {
  match_id: string
  state: LiveStateSnap | null
  history: Tick[]
  match_status: string | null
}

const W = 600
const H = 200
const PAD = { top: 12, right: 8, bottom: 22, left: 28 }

const X_MAX = 95   // 90 + ~5 stoppage typical
const COLORS = {
  home: "#10b981",   // emerald-500
  draw: "#94a3b8",   // slate-400
  away: "#fb923c",   // orange-400
}

function smoothPath(points: Array<[number, number]>): string {
  if (points.length === 0) return ""
  if (points.length === 1) {
    const [x, y] = points[0]
    return `M ${x} ${y}`
  }
  // Light Catmull-Rom-ish smoothing for the line.
  let d = `M ${points[0][0]} ${points[0][1]}`
  for (let i = 1; i < points.length; i++) {
    const [x, y] = points[i]
    const [px, py] = points[i - 1]
    const cx = (px + x) / 2
    d += ` Q ${cx} ${py}, ${cx} ${(py + y) / 2}`
    d += ` T ${x} ${y}`
  }
  return d
}

export function SwingChart({
  matchId,
  homeName,
  awayName,
}: {
  matchId: string
  homeName: string
  awayName: string
}) {
  const [ticks, setTicks] = useState<Tick[]>([])
  const [state, setState] = useState<LiveStateSnap | null>(null)
  const [matchStatus, setMatchStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const esRef = useRef<EventSource | null>(null)

  // 1) First paint: load the full history snapshot.
  useEffect(() => {
    let cancelled = false
    fetch(`/api/live/match/${matchId}/live`)
      .then((r) => r.ok ? r.json() : Promise.reject(r.status))
      .then((data: InitialPayload) => {
        if (cancelled) return
        setTicks(data.history || [])
        setState(data.state)
        setMatchStatus(data.match_status)
      })
      .catch((e) => !cancelled && setError(`Failed to load (${e})`))
    return () => { cancelled = true }
  }, [matchId])

  // 2) Stream new ticks via SSE while the match is live.
  useEffect(() => {
    // Don't open SSE for fully-finished matches — history is enough.
    if (matchStatus === "complete") return
    const es = new EventSource(`/api/live/match/${matchId}/stream`)
    esRef.current = es
    es.addEventListener("tick", (e: MessageEvent) => {
      try {
        const t: Tick = JSON.parse(e.data)
        setTicks((prev) => prev.some((x) => x.id === t.id) ? prev : [...prev, t])
      } catch { /* drop malformed */ }
    })
    es.addEventListener("state", (e: MessageEvent) => {
      try { setState(JSON.parse(e.data)) } catch { /* drop */ }
    })
    es.addEventListener("ended", () => {
      setMatchStatus("complete")
      es.close()
    })
    es.onerror = () => {
      // Browser will auto-reconnect after a short delay; nothing to do.
    }
    return () => { es.close(); esRef.current = null }
  }, [matchId, matchStatus])

  // Project ticks into SVG coordinates.
  const { hPath, dPath, aPath, events, lastTick } = useMemo(() => {
    if (ticks.length === 0) return { hPath: "", dPath: "", aPath: "", events: [], lastTick: null }
    const xs = (m: number) => PAD.left + (m / X_MAX) * (W - PAD.left - PAD.right)
    const ys = (p: number) => PAD.top + (1 - p) * (H - PAD.top - PAD.bottom)
    const home: Array<[number, number]> = []
    const draw: Array<[number, number]> = []
    const away: Array<[number, number]> = []
    const ev: Array<{ x: number; minute: number; label: string }> = []
    for (const t of ticks) {
      const x = xs(t.elapsed_min)
      home.push([x, ys(t.p_home)])
      draw.push([x, ys(t.p_draw)])
      away.push([x, ys(t.p_away)])
      if (t.event_label) ev.push({ x, minute: t.elapsed_min, label: t.event_label })
    }
    return {
      hPath: smoothPath(home),
      dPath: smoothPath(draw),
      aPath: smoothPath(away),
      events: ev,
      lastTick: ticks[ticks.length - 1],
    }
  }, [ticks])

  if (error) {
    return (
      <div className="rounded-2xl border border-edge bg-surface-2 p-5 text-center">
        <p className="text-[12px] text-rose-400">{error}</p>
      </div>
    )
  }

  const live = matchStatus !== "complete" && state?.status && state.status !== "NS"
  const empty = ticks.length === 0
  const nowMinute = state?.elapsed_min ?? lastTick?.elapsed_min ?? 0
  const nowX = PAD.left + (nowMinute / X_MAX) * (W - PAD.left - PAD.right)

  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 overflow-hidden">
      {/* Header */}
      <div className="px-4 pt-3 pb-2 flex items-center justify-between border-b border-edge/40">
        <div className="flex items-center gap-2">
          {live && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-rose-500/15 text-rose-400 rounded-full text-[9px] font-bold tracking-wider uppercase">
              <span className="w-1.5 h-1.5 bg-rose-500 rounded-full animate-pulse" />
              Live
            </span>
          )}
          <p className="text-[12px] font-bold text-white">Win probability</p>
        </div>
        <div className="text-right font-mono">
          {state ? (
            <p className="text-[11px] text-slate-300 tabular-nums">
              {nowMinute}&apos; · {state.home_score ?? 0}–{state.away_score ?? 0}
            </p>
          ) : (
            <p className="text-[11px] text-slate-600">Pre-match</p>
          )}
        </div>
      </div>

      {empty ? (
        <div className="px-4 py-10 text-center">
          <p className="text-[12px] text-slate-500">
            The chart fills in from kickoff. We compute live win probability every 30 seconds.
          </p>
        </div>
      ) : (
        <>
          {/* SVG chart */}
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" preserveAspectRatio="none">
            {/* Y gridlines + labels */}
            {[0, 0.25, 0.5, 0.75, 1].map((p) => {
              const y = PAD.top + (1 - p) * (H - PAD.top - PAD.bottom)
              return (
                <g key={p}>
                  <line
                    x1={PAD.left}
                    y1={y}
                    x2={W - PAD.right}
                    y2={y}
                    stroke="#1a2336"
                    strokeWidth={p === 0.5 ? 1 : 0.5}
                  />
                  <text x={4} y={y + 3} fill="#475569" fontSize="9" fontFamily="monospace">
                    {Math.round(p * 100)}%
                  </text>
                </g>
              )
            })}
            {/* X minute labels at 0, 15, 30, 45, 60, 75, 90 */}
            {[0, 15, 30, 45, 60, 75, 90].map((m) => {
              const x = PAD.left + (m / X_MAX) * (W - PAD.left - PAD.right)
              return (
                <g key={m}>
                  <line
                    x1={x}
                    y1={PAD.top}
                    x2={x}
                    y2={H - PAD.bottom}
                    stroke="#0d1b2a"
                    strokeWidth={m === 45 ? 0.8 : 0.4}
                  />
                  <text x={x - 8} y={H - 6} fill="#475569" fontSize="9" fontFamily="monospace">
                    {m}&apos;
                  </text>
                </g>
              )
            })}

            {/* Lines */}
            <path d={hPath} fill="none" stroke={COLORS.home} strokeWidth={2} strokeLinejoin="round" />
            <path d={dPath} fill="none" stroke={COLORS.draw} strokeWidth={1.5} strokeDasharray="3,3" strokeLinejoin="round" />
            <path d={aPath} fill="none" stroke={COLORS.away} strokeWidth={2} strokeLinejoin="round" />

            {/* "Now" indicator vertical line during live */}
            {live && (
              <line
                x1={nowX}
                y1={PAD.top}
                x2={nowX}
                y2={H - PAD.bottom}
                stroke="#10b981"
                strokeWidth={1}
                strokeDasharray="2,3"
                opacity={0.5}
              />
            )}

            {/* Event markers (goals / reds) */}
            {events.map((e, i) => (
              <g key={i}>
                <circle cx={e.x} cy={PAD.top + 4} r={4} fill="#fbbf24" />
                <text x={e.x + 6} y={PAD.top + 7} fill="#fbbf24" fontSize="8" fontFamily="monospace">
                  {e.minute}&apos;
                </text>
              </g>
            ))}
          </svg>

          {/* Legend + event list */}
          <div className="px-4 py-2 border-t border-edge/40 grid grid-cols-3 gap-2 text-[10px]">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5" style={{ background: COLORS.home }} />
              <span className="text-slate-400 truncate">{homeName}</span>
              {lastTick && (
                <span className="ml-auto font-mono tabular-nums" style={{ color: COLORS.home }}>
                  {Math.round(lastTick.p_home * 100)}%
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 border-t border-dashed" style={{ borderColor: COLORS.draw }} />
              <span className="text-slate-400">Draw</span>
              {lastTick && (
                <span className="ml-auto font-mono tabular-nums" style={{ color: COLORS.draw }}>
                  {Math.round(lastTick.p_draw * 100)}%
                </span>
              )}
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-0.5" style={{ background: COLORS.away }} />
              <span className="text-slate-400 truncate">{awayName}</span>
              {lastTick && (
                <span className="ml-auto font-mono tabular-nums" style={{ color: COLORS.away }}>
                  {Math.round(lastTick.p_away * 100)}%
                </span>
              )}
            </div>
          </div>

          {/* Live stats strip */}
          {state && (state.home_possession != null || state.home_xg != null) && (
            <div className="px-4 py-2 border-t border-edge/40 grid grid-cols-3 gap-3 text-[10px] font-mono tabular-nums">
              {state.home_possession != null && state.away_possession != null && (
                <div>
                  <p className="text-slate-600 uppercase tracking-wider text-[9px] mb-0.5">Possession</p>
                  <p className="text-slate-200">{Math.round(state.home_possession)} / {Math.round(state.away_possession)}</p>
                </div>
              )}
              {(state.home_shots != null || state.away_shots != null) && (
                <div>
                  <p className="text-slate-600 uppercase tracking-wider text-[9px] mb-0.5">Shots (on target)</p>
                  <p className="text-slate-200">
                    {state.home_shots ?? 0}({state.home_shots_on_target ?? 0}) / {state.away_shots ?? 0}({state.away_shots_on_target ?? 0})
                  </p>
                </div>
              )}
              {state.home_xg != null && state.away_xg != null && (
                <div>
                  <p className="text-slate-600 uppercase tracking-wider text-[9px] mb-0.5">xG</p>
                  <p className="text-slate-200">{state.home_xg.toFixed(2)} / {state.away_xg.toFixed(2)}</p>
                </div>
              )}
            </div>
          )}
        </>
      )}

      <div className="px-4 py-2 border-t border-edge/40 flex items-center justify-between gap-2">
        <p className="text-[9px] text-slate-600">
          Updated every 30s. Lines smoothed.
        </p>
        {/* Only surface the share link when there is actually a moment to save.
            Pre-match (status NS, no ticks) the share page is empty so the link
            would deadend a curious user. */}
        {(live || matchStatus === "complete") && ticks.length > 0 && (
          <a
            href={`/share/match-wp/${matchId}`}
            target="_blank"
            rel="noopener"
            className="text-[10px] font-semibold text-emerald-400 hover:text-emerald-300"
          >
            Save this moment →
          </a>
        )}
      </div>
    </div>
  )
}
