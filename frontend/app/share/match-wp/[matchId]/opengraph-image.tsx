/* eslint-disable @next/next/no-img-element */
import { ImageResponse } from "next/og"

export const runtime = "edge"
export const alt = "Live win-probability snapshot"
export const size = { width: 1200, height: 630 }
export const contentType = "image/png"

interface Tick {
  elapsed_min: number
  p_home: number
  p_draw: number
  p_away: number
  home_score: number | null
  away_score: number | null
  event_label: string | null
}

interface MatchData {
  home_name: string
  away_name: string
  ticks: Tick[]
  status: string | null
  elapsed_min: number | null
  home_score: number | null
  away_score: number | null
}

async function fetchMatchData(matchId: string): Promise<MatchData | null> {
  try {
    const backend = process.env.BACKEND_URL ?? "http://wc26-backend:8000"
    const r = await fetch(`${backend}/live/hub/enriched`, { cache: "no-store" })
    if (!r.ok) return null
    const data = await r.json()
    const match = (data.matches ?? []).find((m: any) => m.id === matchId)
    if (!match) return null
    return {
      home_name: match.home_name,
      away_name: match.away_name,
      ticks: match.sparkline ?? [],
      status: match.status,
      elapsed_min: match.elapsed_min,
      home_score: match.home_score,
      away_score: match.away_score,
    }
  } catch {
    return null
  }
}

function buildLinePath(ticks: Tick[], pick: "p_home" | "p_draw" | "p_away",
                       width: number, height: number) {
  if (ticks.length === 0) return ""
  const maxT = Math.max(90, ticks[ticks.length - 1].elapsed_min)
  const x = (t: number) => (t / maxT) * width
  const y = (p: number) => height - p * height
  return ticks
    .map((t, i) => `${i === 0 ? "M" : "L"} ${x(t.elapsed_min).toFixed(1)} ${y(t[pick]).toFixed(1)}`)
    .join(" ")
}

export default async function Image({ params }: { params: { matchId: string } }) {
  const data = await fetchMatchData(params.matchId)

  if (!data) {
    return new ImageResponse(
      (
        <div
          style={{
            background: "#040a0a",
            color: "white",
            width: "100%",
            height: "100%",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            fontFamily: "sans-serif",
          }}
        >
          <p style={{ fontSize: 64, fontWeight: 700 }}>WC26 Predictor</p>
          <p style={{ fontSize: 28, color: "#94a3b8" }}>Match not available right now</p>
        </div>
      ),
      { ...size }
    )
  }

  const CHART_W = 1040
  const CHART_H = 380
  const home_path = buildLinePath(data.ticks, "p_home", CHART_W, CHART_H)
  const draw_path = buildLinePath(data.ticks, "p_draw", CHART_W, CHART_H)
  const away_path = buildLinePath(data.ticks, "p_away", CHART_W, CHART_H)
  const last = data.ticks[data.ticks.length - 1]
  const scoreText = (last?.home_score ?? data.home_score ?? 0) + " - " + (last?.away_score ?? data.away_score ?? 0)
  const minuteText = data.elapsed_min ? `${data.elapsed_min}'` : (data.status ?? "")

  return new ImageResponse(
    (
      <div
        style={{
          background: "linear-gradient(180deg, #040a0a 0%, #071a12 100%)",
          color: "white",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          padding: 50,
          fontFamily: "sans-serif",
        }}
      >
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
          <div style={{ display: "flex", flexDirection: "column" }}>
            <p style={{ fontSize: 18, fontWeight: 700, letterSpacing: 2, color: "#10b981", textTransform: "uppercase", margin: 0 }}>
              Save this moment
            </p>
            <p style={{ fontSize: 44, fontWeight: 800, margin: "6px 0 0 0", color: "white" }}>
              {data.home_name} vs {data.away_name}
            </p>
          </div>
          <div style={{ display: "flex", flexDirection: "column", textAlign: "right" }}>
            <p style={{ fontSize: 56, fontWeight: 800, margin: 0, fontVariantNumeric: "tabular-nums" }}>{scoreText}</p>
            <p style={{ fontSize: 22, color: "#94a3b8", margin: "4px 0 0 0", fontVariantNumeric: "tabular-nums" }}>{minuteText}</p>
          </div>
        </div>

        {/* Chart */}
        <div style={{ marginTop: 40, display: "flex" }}>
          <svg width={CHART_W} height={CHART_H} viewBox={`0 0 ${CHART_W} ${CHART_H}`}>
            {/* gridlines */}
            {[0.25, 0.5, 0.75].map((p) => (
              <line key={p} x1={0} x2={CHART_W} y1={CHART_H * (1 - p)} y2={CHART_H * (1 - p)} stroke="#1e293b" strokeWidth={1} />
            ))}
            {/* lines */}
            <path d={away_path} fill="none" stroke="#f59e0b" strokeWidth={3} />
            <path d={draw_path} fill="none" stroke="#64748b" strokeWidth={3} />
            <path d={home_path} fill="none" stroke="#10b981" strokeWidth={3} />
          </svg>
        </div>

        {/* Legend + brand */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: 32 }}>
          <div style={{ display: "flex", gap: 24, fontSize: 20, alignItems: "center" }}>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ display: "inline-block", width: 14, height: 14, background: "#10b981", borderRadius: 999 }} />
              <span>{data.home_name} ({Math.round((last?.p_home ?? 0) * 100)}%)</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ display: "inline-block", width: 14, height: 14, background: "#64748b", borderRadius: 999 }} />
              <span>Draw ({Math.round((last?.p_draw ?? 0) * 100)}%)</span>
            </span>
            <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <span style={{ display: "inline-block", width: 14, height: 14, background: "#f59e0b", borderRadius: 999 }} />
              <span>{data.away_name} ({Math.round((last?.p_away ?? 0) * 100)}%)</span>
            </span>
          </div>
          <p style={{ fontSize: 22, color: "#10b981", fontWeight: 700, margin: 0 }}>wc26.tinjak.com</p>
        </div>
      </div>
    ),
    { ...size }
  )
}
