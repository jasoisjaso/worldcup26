/**
 * Vertical 9:16 share card for /match/[id] — 1080x1920 PNG.
 *
 * URL pattern: GET /match/{id}/share -> image/png
 * Use case: TikTok / Instagram Reels / Stories overlays. The download button
 * on the match page links here with a friendly filename.
 *
 * We use the Node runtime (not edge) because the deployment is a docker
 * container; @vercel/og works fine in Node too. Flag images come from flagcdn
 * which is already allowed in next.config.mjs.
 */
import { ImageResponse } from "next/og"

export const runtime = "nodejs"
export const dynamic = "force-dynamic"
export const revalidate = 300 // 5 min — predictions don't move that often

const BASE =
  typeof process !== "undefined" && process.env.BACKEND_URL
    ? process.env.BACKEND_URL
    : "http://wc26-backend:8000"

type Team = {
  code: string
  name: string
  flag_url?: string | null
  primary_color?: string | null
}

type Match = {
  id: string
  group: string
  matchday: number
  kickoff: string
  status: "upcoming" | "live" | "complete"
  home: Team
  away: Team
  actual_score?: { home: number; away: number } | null
}

type Prediction = {
  home_win: number
  draw: number
  away_win: number
  top_scores: Array<{ home: number; away: number; prob: number }>
}

async function fetchMatch(id: string): Promise<{ match: Match | null; pred: Prediction | null }> {
  try {
    const [matchRes, predRes] = await Promise.all([
      fetch(`${BASE}/matches/${id}`, { cache: "no-store" }),
      fetch(`${BASE}/matches/${id}/prediction`, { cache: "no-store" }),
    ])
    const match = matchRes.ok ? ((await matchRes.json()) as Match) : null
    const pred = predRes.ok ? ((await predRes.json()) as Prediction) : null
    return { match, pred }
  } catch {
    return { match: null, pred: null }
  }
}

function pct(p: number | null | undefined): string {
  if (p == null) return "—"
  return `${Math.round(p * 100)}%`
}

function verdictLine(pred: Prediction | null): { label: string; tone: "home" | "draw" | "away" } {
  if (!pred) return { label: "Coming soon", tone: "draw" }
  const max = Math.max(pred.home_win, pred.draw, pred.away_win)
  if (max === pred.home_win) return { label: "Home edge", tone: "home" }
  if (max === pred.away_win) return { label: "Away edge", tone: "away" }
  return { label: "Honours even", tone: "draw" }
}

function formatKickoff(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString("en-AU", {
      timeZone: "Australia/Brisbane",
      weekday: "short",
      day: "numeric",
      month: "short",
      hour: "numeric",
      minute: "2-digit",
      hour12: false,
    })
  } catch {
    return iso.slice(0, 16).replace("T", " ")
  }
}

export async function GET(_req: Request, { params }: { params: { id: string } }) {
  const { match, pred } = await fetchMatch(params.id)

  // Fallback card when match is missing — still valid PNG so social previews don't 404.
  if (!match) {
    return new ImageResponse(
      (
        <div
          style={{
            width: "100%",
            height: "100%",
            background: "#0a0f1a",
            color: "#fff",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 56,
            fontWeight: 700,
          }}
        >
          wc26.tinjak.com
        </div>
      ),
      { width: 1080, height: 1920 },
    )
  }

  const verdict = verdictLine(pred)
  const top = pred?.top_scores?.[0]
  const isComplete = match.status === "complete" && match.actual_score
  const homeColor = match.home.primary_color || "#10b981"
  const awayColor = match.away.primary_color || "#3b82f6"

  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "linear-gradient(180deg, #050810 0%, #0a0f1a 60%, #050810 100%)",
          color: "#fff",
          display: "flex",
          flexDirection: "column",
          padding: 64,
          fontFamily: '"Inter", "system-ui", sans-serif',
        }}
      >
        {/* Top wordmark */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                width: 36,
                height: 36,
                borderRadius: 999,
                background: "#10b981",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontSize: 22,
                fontWeight: 800,
                color: "#050810",
              }}
            >
              ⚽
            </div>
            <div style={{ fontSize: 26, fontWeight: 800, color: "#fff", letterSpacing: -0.5 }}>
              wc26.tinjak.com
            </div>
          </div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: "#10b981",
              background: "rgba(16, 185, 129, 0.12)",
              padding: "8px 18px",
              borderRadius: 999,
              border: "1px solid rgba(16, 185, 129, 0.4)",
            }}
          >
            Group {match.group} · MD{match.matchday}
          </div>
        </div>

        {/* Hero: flags + scoreline */}
        <div
          style={{
            flex: 1,
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            gap: 36,
          }}
        >
          {/* Two flags row */}
          <div style={{ display: "flex", alignItems: "center", gap: 80 }}>
            {/* Home */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
              {match.home.flag_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={match.home.flag_url}
                  alt=""
                  width={220}
                  height={150}
                  style={{ borderRadius: 16, objectFit: "cover", border: `4px solid ${homeColor}` }}
                />
              ) : (
                <div style={{ width: 220, height: 150, background: homeColor, borderRadius: 16 }} />
              )}
              <div style={{ fontSize: 40, fontWeight: 800, color: "#fff", letterSpacing: -0.5 }}>
                {match.home.name}
              </div>
            </div>

            <div style={{ fontSize: 64, fontWeight: 900, color: "#475569", letterSpacing: -2 }}>vs</div>

            {/* Away */}
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 18 }}>
              {match.away.flag_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={match.away.flag_url}
                  alt=""
                  width={220}
                  height={150}
                  style={{ borderRadius: 16, objectFit: "cover", border: `4px solid ${awayColor}` }}
                />
              ) : (
                <div style={{ width: 220, height: 150, background: awayColor, borderRadius: 16 }} />
              )}
              <div style={{ fontSize: 40, fontWeight: 800, color: "#fff", letterSpacing: -0.5 }}>
                {match.away.name}
              </div>
            </div>
          </div>

          {/* Actual score for completed matches, else probability bars */}
          {isComplete && match.actual_score ? (
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 8 }}>
              <div style={{ fontSize: 28, color: "#94a3b8", fontWeight: 600 }}>Final score</div>
              <div style={{ fontSize: 200, fontWeight: 900, color: "#fff", letterSpacing: -8, lineHeight: 1 }}>
                {match.actual_score.home} – {match.actual_score.away}
              </div>
            </div>
          ) : (
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "stretch",
                width: 880,
                gap: 18,
                marginTop: 12,
              }}
            >
              <div style={{ fontSize: 26, color: "#94a3b8", fontWeight: 600, textAlign: "center" }}>
                Our model says
              </div>

              {/* Probability row */}
              <div style={{ display: "flex", gap: 18 }}>
                <ProbCol label={match.home.code.toUpperCase()} value={pct(pred?.home_win)} color={homeColor} />
                <ProbCol label="DRAW" value={pct(pred?.draw)} color="#64748b" />
                <ProbCol label={match.away.code.toUpperCase()} value={pct(pred?.away_win)} color={awayColor} />
              </div>

              {top && (
                <div
                  style={{
                    fontSize: 32,
                    color: "#cbd5e1",
                    textAlign: "center",
                    marginTop: 16,
                    fontWeight: 600,
                  }}
                >
                  Most likely score:{" "}
                  <span style={{ color: "#10b981", fontWeight: 800 }}>
                    {top.home} – {top.away}
                  </span>{" "}
                  <span style={{ color: "#64748b", fontSize: 26 }}>({pct(top.prob)})</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Bottom strip */}
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            borderTop: "1px solid #1e293b",
            paddingTop: 32,
          }}
        >
          <div style={{ display: "flex", flexDirection: "column" }}>
            <div style={{ fontSize: 20, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: 1.5 }}>
              {isComplete ? "Full time" : "Kickoff (Brisbane)"}
            </div>
            <div style={{ fontSize: 28, color: "#e2e8f0", fontWeight: 700, marginTop: 4 }}>
              {isComplete ? "Result final" : formatKickoff(match.kickoff)}
            </div>
          </div>
          <div
            style={{
              fontSize: 22,
              fontWeight: 700,
              color: verdict.tone === "home" ? homeColor : verdict.tone === "away" ? awayColor : "#94a3b8",
              padding: "12px 22px",
              borderRadius: 14,
              background: "rgba(255,255,255,0.04)",
              border: "1px solid #1e293b",
            }}
          >
            {verdict.label}
          </div>
        </div>
      </div>
    ),
    { width: 1080, height: 1920 },
  )
}

function ProbCol({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div
      style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        padding: 28,
        borderRadius: 18,
        background: "rgba(255,255,255,0.04)",
        border: `1px solid ${color}55`,
        gap: 8,
      }}
    >
      <div style={{ fontSize: 22, fontWeight: 700, color: "#64748b", letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 72, fontWeight: 900, color, letterSpacing: -2, lineHeight: 1 }}>{value}</div>
    </div>
  )
}
