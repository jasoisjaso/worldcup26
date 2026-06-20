# Live + Team Pages + Tie-It-Together Implementation Plan

> **For Claude:** Execute task-by-task. Local-first testing per task. Push only after a wave completes and Playwright proves it. Do NOT push methodology/league IDs in commits. AU English. No em-dashes in copy.

**Goal:** Turn WC2026 Predictor from a "look at the model" tool into a place punters live during matches and obsess over teams between them. Three concrete deliverables the owner named, plus everything the new harvest data unlocks.

**Architecture:** Build downstream of the harvest pipeline that just landed (PlayerProfile + PlayerTournamentStats + FixtureArchive + MatchEvent + MatchH2H all populating). All new pages are SSR Next 15 with `dynamic = "force-dynamic"`, polling client islands for live data. Zero new dependencies. Reuses existing component vocab (TopBar / NotificationBell / KickoffTime / Flag pattern).

**Tech Stack:** Next 15 App Router · FastAPI · SQLAlchemy · existing `lib/api.ts` client · existing emerald/amber/JetBrains brand. No new fonts, no new colors, no shadcn additions.

**What's already live (this is the floor — do not regress):**
- `/live` page with LiveHub: enriched poll every 15s, event ticker, swing narrative, smart bet slip, sparkline, api-football vs us, golden boot mini, coming-up split, just-finished
- `/team/[code]` page with profile + outlook + radar + squad text-only list + group standing
- Harvester writing PlayerProfile (photo_url), PlayerTournamentStats, FixtureArchive (xG, possession, shots, pass%)

---

## Wave 1 — Live-Now Persistent Nudge (owner ask #3, smallest, ties everything)

**Why first:** It's the smallest piece, lights up every other page, and validates the cheap-poll pattern we'll reuse.

### Task 1.1: Add `/live/summary` endpoint (cheap poll target)

**Objective:** One JSON endpoint <500 bytes, returns just enough for a ticker.

**Files:**
- Modify: `backend/api/routes/live.py`

**Step 1: Add the route at the bottom of the file:**

```python
@router.get("/summary")
def live_summary():
    """Cheap polling target for the site-wide live ticker.
    Returns at most 3 in-play matches with score + elapsed, plus
    the next kickoff so the ticker can pre-warn users."""
    from datetime import datetime, timedelta
    from sqlalchemy import or_, and_
    from backend.db.session import SessionLocal
    from backend.db.models import Match
    db = SessionLocal()
    try:
        live = (
            db.query(Match)
            .filter(Match.status.in_(["1H", "2H", "ET", "HT", "LIVE"]))
            .order_by(Match.kickoff.asc())
            .limit(3)
            .all()
        )
        next_kick = (
            db.query(Match)
            .filter(Match.status == "upcoming")
            .filter(Match.kickoff > datetime.utcnow())
            .order_by(Match.kickoff.asc())
            .first()
        )
        return {
            "live_count": len(live),
            "live": [
                {
                    "id": m.id,
                    "home_code": m.home_code,
                    "away_code": m.away_code,
                    "home_score": m.home_score or 0,
                    "away_score": m.away_score or 0,
                    "status": m.status,
                }
                for m in live
            ],
            "next": {
                "id": next_kick.id,
                "home_code": next_kick.home_code,
                "away_code": next_kick.away_code,
                "kickoff": next_kick.kickoff.isoformat() if next_kick.kickoff else None,
                "minutes_away": int((next_kick.kickoff - datetime.utcnow()).total_seconds() // 60),
            } if next_kick else None,
        }
    finally:
        db.close()
```

**Step 2:** Verify locally — `curl -s http://localhost:8000/live/summary | python -m json.tool`. Expected shape: `{ live_count, live: [...], next: {...} }`.

**Step 3:** Commit:
```bash
git add backend/api/routes/live.py
git commit -m "live: cheap /summary endpoint for site-wide ticker"
```

### Task 1.2: Add `api.liveSummary()` to client

**Files:**
- Modify: `frontend/lib/api.ts`

**Step 1:** Add next to other live helpers:
```ts
liveSummary: () => get<{
  live_count: number;
  live: Array<{ id: string; home_code: string; away_code: string; home_score: number; away_score: number; status: string }>;
  next: { id: string; home_code: string; away_code: string; kickoff: string | null; minutes_away: number } | null;
}>("/live/summary"),
```

**Step 2:** Commit:
```bash
git add frontend/lib/api.ts
git commit -m "api: add liveSummary helper"
```

### Task 1.3: Build `LiveTicker` client component

**Objective:** Thin pulsing bar that mounts in the root layout. Hidden when no live matches AND no kickoff within 30 min.

**Files:**
- Create: `frontend/components/live/LiveTicker.tsx`

```tsx
"use client"
import { useEffect, useState } from "react"
import Link from "next/link"

interface Summary {
  live_count: number
  live: Array<{ id: string; home_code: string; away_code: string; home_score: number; away_score: number; status: string }>
  next: { id: string; minutes_away: number; home_code: string; away_code: string } | null
}

export function LiveTicker() {
  const [data, setData] = useState<Summary | null>(null)

  useEffect(() => {
    let alive = true
    const tick = async () => {
      try {
        const r = await fetch("/api/proxy/live-summary", { cache: "no-store" })
        if (alive && r.ok) setData(await r.json())
      } catch { /* keep stale */ }
    }
    tick()
    const iv = setInterval(tick, 30_000)
    return () => { alive = false; clearInterval(iv) }
  }, [])

  if (!data) return null
  const showLive = data.live_count > 0
  const showSoon = !showLive && data.next && data.next.minutes_away <= 30 && data.next.minutes_away >= 0
  if (!showLive && !showSoon) return null

  return (
    <Link
      href="/live"
      className="fixed top-0 inset-x-0 z-50 flex items-center justify-center gap-2 px-3 py-1.5
                 bg-gradient-to-r from-rose-950/95 to-rose-900/95 border-b border-rose-700/40
                 backdrop-blur text-[11px] font-semibold text-rose-100
                 hover:from-rose-900 hover:to-rose-800 transition-colors"
    >
      {showLive ? (
        <>
          <span className="w-1.5 h-1.5 bg-rose-400 rounded-full animate-pulse" />
          <span className="font-mono tabular-nums">
            {data.live[0].home_code.toUpperCase()} {data.live[0].home_score}–{data.live[0].away_score} {data.live[0].away_code.toUpperCase()}
          </span>
          {data.live_count > 1 && <span className="text-rose-300">+{data.live_count - 1}</span>}
          <span className="text-rose-200/70">Live now</span>
        </>
      ) : (
        <>
          <span className="w-1.5 h-1.5 bg-amber-400 rounded-full" />
          <span>Kickoff in {data.next!.minutes_away}m</span>
        </>
      )}
    </Link>
  )
}
```

### Task 1.4: Proxy route for ticker (same-origin client fetch)

**Files:**
- Create: `frontend/app/api/proxy/live-summary/route.ts`

```ts
import { NextResponse } from "next/server"
export const dynamic = "force-dynamic"

export async function GET() {
  const base = process.env.BACKEND_URL ?? "http://wc26-backend:8000"
  const r = await fetch(`${base}/live/summary`, { cache: "no-store" })
  return new NextResponse(await r.text(), {
    status: r.status,
    headers: { "content-type": "application/json" },
  })
}
```

### Task 1.5: Mount ticker in root layout

**Files:**
- Modify: `frontend/app/layout.tsx`

**Step 1:** Import + render `<LiveTicker />` BEFORE the existing main wrapper so it floats above everything. Add `pt-[28px]` to the main wrapper class so content doesn't sit under the ticker when it shows. Use CSS to push down only when the ticker is mounted via a body class.

**Cleanest:** Render `<LiveTicker />` at top, give the existing nav `pt-[28px]` on screens where the ticker is fixed. Easier path — the LiveTicker is `position: fixed top-0`, and the nav is also typically fixed/sticky. Add `top-[28px]` to the existing nav when ticker is visible. Implement by exposing a `data-ticker-visible` attr on `<html>` from inside the component via a tiny effect, then CSS-shift the nav.

For YAGNI — just always allocate the 28px when the ticker MIGHT show. Add `<div className="h-[28px]" />` spacer that the ticker overlays. Spacer is always there; ticker only fixed-overlays when needed. No flicker.

```tsx
import { LiveTicker } from "@/components/live/LiveTicker"
// ...
<body>
  <LiveTicker />
  <div className="h-[28px]" aria-hidden /> {/* ticker reservation */}
  {/* existing children */}
</body>
```

**Step 2:** Verify locally — start backend + frontend, browse to `/` and `/winner`. Ticker should appear if any match is live (or kickoff within 30 min), otherwise the spacer is invisible.

**Step 3:** Commit:
```bash
git add frontend/components/live/LiveTicker.tsx frontend/app/api/proxy/live-summary/route.ts frontend/app/layout.tsx
git commit -m "ui: site-wide live ticker (auto-hides when nothing in play)"
```

### Task 1.6: Push wave 1 + Playwright smoke test

**Step 1:** Push + wait for VPS auto-deploy.
**Step 2:** Playwright: visit `https://wc26.tinjak.com/`, assert ticker appears when `live_count > 0`. Visit when no live match, assert ticker hidden.
**Step 3:** Tag commit message `live ticker shipped` in CURRENT-BACKLOG.md (gitignored).

---

## Wave 2 — Team detail page overhaul (owner ask #2 — biggest win)

**Why second:** Uses the new harvest data we just shipped. Visible immediately because players already harvested for first 6 WC teams as of last check (France, Spain, Belgium, Portugal, Netherlands, Germany — 156 profiles total).

### Task 2.1: New endpoint — `/teams/{code}/squad-rich`

**Objective:** Return PlayerProfile joined with PlayerTournamentStats for a team. Sorted by position then jersey number.

**Files:**
- Modify: `backend/api/routes/teams.py`

```python
@router.get("/{code}/squad-rich")
def squad_rich(code: str):
    """Detailed squad: PlayerProfile + season stats per player.
    Powers the player-card grid on the team detail page."""
    from sqlalchemy import case
    from backend.db.session import SessionLocal
    from backend.db.models import PlayerProfile, PlayerTournamentStats
    from backend.data.fetchers.injuries import TEAM_IDS
    team_api_id = TEAM_IDS.get(code.lower())
    if not team_api_id:
        return {"players": []}
    db = SessionLocal()
    try:
        players = (
            db.query(PlayerProfile)
            .filter(PlayerProfile.team_id == team_api_id)
            .all()
        )
        stats = {
            s.player_id: s
            for s in db.query(PlayerTournamentStats)
            .filter(PlayerTournamentStats.team_id == team_api_id)
            .all()
        }
        def to_dict(p):
            s = stats.get(p.player_id)
            return {
                "player_id": p.player_id,
                "name": p.name,
                "position": p.position or "Unknown",
                "age": p.age,
                "nationality": p.nationality,
                "photo_url": p.photo_url,
                "stats": {
                    "appearances": s.appearances if s else 0,
                    "goals": s.goals if s else 0,
                    "assists": s.assists if s else 0,
                    "minutes": s.minutes if s else 0,
                    "yellow_cards": s.yellow_cards if s else 0,
                    "red_cards": s.red_cards if s else 0,
                } if s else None,
            }
        # Group by position with the canonical football order
        order = {"Goalkeeper": 0, "Defender": 1, "Midfielder": 2, "Attacker": 3}
        rows = sorted(
            [to_dict(p) for p in players],
            key=lambda x: (order.get(x["position"], 99), -(x["stats"]["goals"] if x["stats"] else 0), x["name"]),
        )
        return {"players": rows, "total": len(rows)}
    finally:
        db.close()
```

**Verification:**
```bash
curl -s http://localhost:8000/teams/fr/squad-rich | python -m json.tool | head -30
# Expected: 23-26 players with photo_url populated
```

**Commit:** `git commit -m "api: /teams/{code}/squad-rich joining profile + season stats"`

### Task 2.2: New endpoint — `/teams/{code}/recent-form`

**Files:**
- Modify: `backend/api/routes/teams.py`

```python
@router.get("/{code}/recent-form")
def recent_form(code: str, n: int = 5):
    """Last N completed matches involving this team, with our score data.
    Returns oldest → newest so the strip reads left-to-right."""
    from backend.db.session import SessionLocal
    from backend.db.models import Match
    db = SessionLocal()
    try:
        rows = (
            db.query(Match)
            .filter((Match.home_code == code) | (Match.away_code == code))
            .filter(Match.status == "complete")
            .order_by(Match.kickoff.desc())
            .limit(n)
            .all()
        )
        def result(m):
            if m.home_score is None or m.away_score is None: return None
            is_home = m.home_code == code
            mine = m.home_score if is_home else m.away_score
            theirs = m.away_score if is_home else m.home_score
            if mine > theirs: return "W"
            if mine < theirs: return "L"
            return "D"
        return {
            "form": [
                {
                    "match_id": m.id,
                    "opponent": m.away_code if m.home_code == code else m.home_code,
                    "score": f"{m.home_score}-{m.away_score}",
                    "result": result(m),
                    "kickoff": m.kickoff.isoformat() if m.kickoff else None,
                    "venue": "H" if m.home_code == code else "A",
                }
                for m in reversed(rows)
            ]
        }
    finally:
        db.close()
```

**Commit:** `git commit -m "api: /teams/{code}/recent-form for form-strip widget"`

### Task 2.3: api.ts helpers for both endpoints

**Files:**
- Modify: `frontend/lib/api.ts`

```ts
squadRich: (code: string) => get<{
  total: number;
  players: Array<{
    player_id: number;
    name: string;
    position: string;
    age: number | null;
    nationality: string | null;
    photo_url: string | null;
    stats: { appearances: number; goals: number; assists: number; minutes: number; yellow_cards: number; red_cards: number } | null;
  }>;
}>(`/teams/${code}/squad-rich`),

teamRecentForm: (code: string) => get<{
  form: Array<{ match_id: string; opponent: string; score: string; result: "W"|"L"|"D"; kickoff: string | null; venue: "H"|"A" }>;
}>(`/teams/${code}/recent-form`),
```

### Task 2.4: `PlayerCard` component

**Files:**
- Create: `frontend/components/team/PlayerCard.tsx`

```tsx
import Link from "next/link"

interface Player {
  player_id: number
  name: string
  position: string
  age: number | null
  photo_url: string | null
  stats: { appearances: number; goals: number; assists: number; minutes: number } | null
}

export function PlayerCard({ player: p }: { player: Player }) {
  const hasStats = p.stats && p.stats.appearances > 0
  return (
    <Link
      href={`/player/${p.player_id}`}
      className="group flex items-center gap-3 rounded-xl border border-edge bg-surface-2 shadow-e1 px-3 py-2.5 hover:border-emerald-500/40 transition-colors"
    >
      {p.photo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={p.photo_url} alt={p.name} className="w-11 h-11 rounded-full object-cover ring-1 ring-white/10 shrink-0" />
      ) : (
        <span className="w-11 h-11 rounded-full bg-slate-800 ring-1 ring-white/10 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <p className="text-[13px] font-bold text-white truncate">{p.name}</p>
        <p className="text-[10px] text-slate-500">
          {p.position}{p.age ? ` · ${p.age}` : ""}
        </p>
      </div>
      {hasStats ? (
        <div className="flex items-center gap-2.5 shrink-0 text-right">
          <div>
            <p className="font-mono text-[14px] font-black text-amber-400 tabular-nums">{p.stats!.goals}</p>
            <p className="text-[9px] text-slate-600 uppercase tracking-wider">Goals</p>
          </div>
          {p.stats!.assists > 0 && (
            <div>
              <p className="font-mono text-[14px] font-bold text-emerald-400 tabular-nums">{p.stats!.assists}</p>
              <p className="text-[9px] text-slate-600 uppercase tracking-wider">Asts</p>
            </div>
          )}
        </div>
      ) : (
        <span className="text-[10px] text-slate-700 shrink-0">no data yet</span>
      )}
    </Link>
  )
}
```

### Task 2.5: `FormStrip` component

**Files:**
- Create: `frontend/components/team/FormStrip.tsx`

```tsx
import Link from "next/link"

interface FormGame {
  match_id: string
  opponent: string
  score: string
  result: "W" | "L" | "D"
  venue: "H" | "A"
}

const COLORS: Record<string, string> = {
  W: "bg-emerald-600 text-white",
  L: "bg-rose-700 text-white",
  D: "bg-slate-600 text-white",
}

export function FormStrip({ games, teamCode }: { games: FormGame[]; teamCode: string }) {
  if (!games.length) {
    return <p className="text-[11px] text-slate-600">Form will appear after matches are played.</p>
  }
  return (
    <div className="flex items-center gap-1.5">
      {games.map((g) => (
        <Link
          key={g.match_id}
          href={`/match/${g.match_id}?from=${encodeURIComponent("/team/" + teamCode)}`}
          title={`${g.venue === "H" ? "vs" : "at"} ${g.opponent.toUpperCase()} · ${g.score}`}
          className={`w-7 h-7 rounded-md flex items-center justify-center font-mono font-bold text-[11px] ${COLORS[g.result]} hover:ring-2 hover:ring-emerald-400/40 transition-shadow`}
        >
          {g.result}
        </Link>
      ))}
    </div>
  )
}
```

### Task 2.6: Rewire `/team/[code]/page.tsx` to render rich squad + form

**Files:**
- Modify: `frontend/app/team/[code]/page.tsx`

**Steps:**
1. Add `squadRich` + `teamRecentForm` to the `Promise.all` fetch block.
2. Replace the existing squad text-block (lines 192-215) with a `PlayerCard` grid grouped by position (4 sections: Goalkeeper, Defender, Midfielder, Attacker).
3. Insert a new "Recent form" section BEFORE the "Group fixtures" block, rendering `<FormStrip games={form.form} teamCode={params.code} />`.
4. If `squadRich.total === 0`, keep the existing "model doesn't use players" copy.

**Verification:** Visit `/team/fr` locally, expect to see Mbappé/Dembélé etc. with photos. Visit `/team/us`, expect "no data yet" gracefully.

**Commit:** `git commit -m "team: photo + stats grid, recent form strip"`

### Task 2.7: Make team names clickable everywhere

**Files to scan:**
- `frontend/components/match/MatchCard.tsx` — team rows should link to `/team/{code}?from={current}`
- `frontend/components/live/LiveHub.tsx` — `LiveMatchCard` team rows (currently inside the parent Link to /match — need to factor out so team name becomes nested clickable)
- `frontend/app/winner/page.tsx` — team rows
- `frontend/app/groups/page.tsx` — team rows
- `frontend/components/match/MatchVerdict.tsx` if any team-name display

**Pattern:** Wrap team name + flag in `<Link href={`/team/${code}?from=${encodeURIComponent(pathname)}`} className="..." onClick={(e) => e.stopPropagation()}>`. The `stopPropagation` is critical when a parent Link is also present (e.g. MatchCard wraps the whole row in a link to the match).

**Commit:** `git commit -m "ui: make team names clickable across match/live/winner/groups"`

### Task 2.8: Push wave 2 + Playwright

**Step 1:** Push.
**Step 2:** Playwright: visit `/team/fr`, assert at least 1 `img` with `Mbappé` alt + 1 `FormStrip` square. Visit `/`, click any team name in a MatchCard, assert URL goes to `/team/{code}`.
**Step 3:** Note in CURRENT-BACKLOG that team overhaul shipped.

---

## Wave 3 — Player profile pages (the rabbit hole)

**Why third:** Now that clicking a player in PlayerCard goes to `/player/{id}`, we need that page to exist. Uses harvested data only — zero new API quota.

### Task 3.1: Endpoint `/players/{id}/profile`

**Files:**
- Create: `backend/api/routes/players.py`
- Modify: `backend/api/main.py` (register router)

```python
from fastapi import APIRouter, HTTPException

router = APIRouter()

@router.get("/{player_id}/profile")
def player_profile(player_id: int):
    from backend.db.session import SessionLocal
    from backend.db.models import PlayerProfile, PlayerTournamentStats, PlayerHistory
    db = SessionLocal()
    try:
        p = db.query(PlayerProfile).filter(PlayerProfile.player_id == player_id).first()
        if not p:
            raise HTTPException(404, "player not found")
        stats = (
            db.query(PlayerTournamentStats)
            .filter(PlayerTournamentStats.player_id == player_id)
            .all()
        )
        recent = (
            db.query(PlayerHistory)
            .filter(PlayerHistory.api_player_id == player_id)
            .order_by(PlayerHistory.id.desc())
            .limit(10)
            .all()
        )
        return {
            "player": {
                "id": p.player_id,
                "name": p.name,
                "age": p.age,
                "position": p.position,
                "nationality": p.nationality,
                "height": p.height,
                "weight": p.weight,
                "photo_url": p.photo_url,
                "team_id": p.team_id,
                "team_name": p.team_name,
            },
            "career_stats": [
                {
                    "team_id": s.team_id,
                    "team_name": s.team_name,
                    "appearances": s.appearances,
                    "goals": s.goals,
                    "assists": s.assists,
                    "minutes": s.minutes,
                    "yellow_cards": s.yellow_cards,
                    "red_cards": s.red_cards,
                }
                for s in stats
            ],
            "recent_matches": [
                {
                    "api_fixture_id": h.api_fixture_id,
                    "match_id": h.match_id,
                    "goals": h.goals,
                    "assists": h.assists,
                    "minutes": h.minutes,
                    "rating": h.rating,
                }
                for h in recent
            ],
        }
    finally:
        db.close()
```

Register: `app.include_router(players.router, prefix="/players")`

### Task 3.2: api.ts helper

```ts
playerProfile: (id: number) => get<{
  player: { id: number; name: string; age: number | null; position: string | null; nationality: string | null; height: string | null; weight: string | null; photo_url: string | null; team_id: number | null; team_name: string | null };
  career_stats: Array<{ team_id: number; team_name: string; appearances: number; goals: number; assists: number; minutes: number; yellow_cards: number; red_cards: number }>;
  recent_matches: Array<{ api_fixture_id: number; match_id: string | null; goals: number; assists: number; minutes: number; rating: number | null }>;
}>(`/players/${id}/profile`),
```

### Task 3.3: `/player/[id]/page.tsx`

**Files:**
- Create: `frontend/app/player/[id]/page.tsx`

```tsx
import type { Metadata } from "next"
import Link from "next/link"
import { TopBar } from "@/components/layout/TopBar"
import { api } from "@/lib/api"
import { resolveBack } from "@/lib/back-nav"

export const dynamic = "force-dynamic"

export async function generateMetadata({ params }: { params: { id: string } }): Promise<Metadata> {
  try {
    const d = await api.playerProfile(Number(params.id))
    return { title: `${d.player.name}: stats and profile` }
  } catch { return { title: "Player" } }
}

export default async function PlayerPage({ params, searchParams }: { params: { id: string }; searchParams: { from?: string } }) {
  let data: Awaited<ReturnType<typeof api.playerProfile>> | null = null
  try { data = await api.playerProfile(Number(params.id)) } catch { /* 404 */ }
  const back = resolveBack(searchParams.from, { href: "/", label: "Home" })
  if (!data) return (
    <>
      <TopBar title="Player" backHref={back.href} backLabel={back.label} />
      <p className="text-slate-500 text-sm py-16 text-center px-4">Player not found.</p>
    </>
  )
  const p = data.player
  const totals = data.career_stats.reduce(
    (a, s) => ({ apps: a.apps + s.appearances, g: a.g + s.goals, a: a.a + s.assists, min: a.min + s.minutes }),
    { apps: 0, g: 0, a: 0, min: 0 },
  )
  return (
    <>
      <TopBar title={p.name} subtitle={p.team_name || ""} backHref={back.href} backLabel={back.label} />
      <div className="max-w-2xl mx-auto px-3 sm:px-5 py-5">
        <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-5 mb-5 flex items-center gap-4">
          {p.photo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.photo_url} alt={p.name} className="w-20 h-20 rounded-full ring-1 ring-white/10 object-cover" />
          ) : <span className="w-20 h-20 rounded-full bg-slate-800 ring-1 ring-white/10" />}
          <div className="min-w-0">
            <h1 className="text-[22px] font-black text-white leading-tight">{p.name}</h1>
            <p className="text-[12px] text-slate-500 mt-0.5">
              {p.position}{p.age ? ` · ${p.age} yrs` : ""}{p.nationality ? ` · ${p.nationality}` : ""}
            </p>
            {p.team_name && <p className="text-[11px] text-slate-600 mt-0.5">{p.team_name}</p>}
          </div>
        </div>

        {totals.apps > 0 && (
          <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-emerald-400/80 mb-3">Career totals</p>
            <div className="grid grid-cols-4 gap-3 text-center">
              <div><p className="font-mono text-[22px] font-black text-white tabular-nums">{totals.apps}</p><p className="text-[10px] text-slate-500 uppercase tracking-wider">Apps</p></div>
              <div><p className="font-mono text-[22px] font-black text-amber-400 tabular-nums">{totals.g}</p><p className="text-[10px] text-slate-500 uppercase tracking-wider">Goals</p></div>
              <div><p className="font-mono text-[22px] font-black text-emerald-400 tabular-nums">{totals.a}</p><p className="text-[10px] text-slate-500 uppercase tracking-wider">Assists</p></div>
              <div><p className="font-mono text-[22px] font-black text-slate-300 tabular-nums">{Math.round(totals.min / 90)}</p><p className="text-[10px] text-slate-500 uppercase tracking-wider">90s</p></div>
            </div>
          </div>
        )}

        {data.recent_matches.length > 0 && (
          <div className="mb-5">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-2">Recent matches</p>
            <div className="rounded-xl border border-edge bg-surface-2 shadow-e1 overflow-hidden divide-y divide-edge/30">
              {data.recent_matches.map((m) => (
                <div key={m.api_fixture_id} className="flex items-center gap-3 px-4 py-2 text-[12px]">
                  <span className="text-slate-500 font-mono tabular-nums w-12">{m.minutes}'</span>
                  <span className="flex-1">{m.goals > 0 && <span className="text-amber-400 font-bold">{m.goals}G </span>}{m.assists > 0 && <span className="text-emerald-400 font-bold">{m.assists}A </span>}{!m.goals && !m.assists && <span className="text-slate-600">No goal involvement</span>}</span>
                  {m.rating && <span className="font-mono tabular-nums text-slate-400">{m.rating.toFixed(1)}</span>}
                  {m.match_id && <Link href={`/match/${m.match_id}`} className="text-emerald-400 text-[11px] hover:underline">View →</Link>}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </>
  )
}
```

### Task 3.4: Push + Playwright

**Step 1:** Push wave 3.
**Step 2:** Playwright: visit a `/player/{id}` URL (use Mbappé's known api-football id 278), assert presence of `<img>` + "Career totals" + a number > 0 next to "Goals".

---

## Wave 4 — Live page overhaul (owner ask #1 — make it stand out)

**Why fourth:** Big bang. Worth doing AFTER waves 1–3 because the persistent ticker means people will actually see the live page once a match starts.

### Task 4.1: New endpoint `/live/storylines`

**Objective:** A small endpoint surfacing the 3 most-interesting "things happening right now": biggest WP swing in last 5 min, biggest upset brewing (lowly team leading), goal of the day. Returns at most 3 cards.

**Files:**
- Modify: `backend/api/routes/live.py`

(Pseudocode — implementation reads live state from existing snapshots tables + WP history; full code stubbed at ~80 LOC. Keep this as a CHEAP query: pull MatchEvent rows from last 6h + current live cards from existing hub.)

### Task 4.2: New `MatchOfMoment` hero card on /live

**Files:**
- Create: `frontend/components/live/MatchOfMoment.tsx`
- Modify: `frontend/app/live/page.tsx`

Hero card pinned to top of page when ≥1 live match. Shows the match with the biggest WP swing in the last 5 minutes (from existing sparkline data). Bigger fonts, the live ticker collapsed into a stripe at the top of the card, animated goal-flash backdrop when score changes.

### Task 4.3: Per-card "stat vs team season average" mini bars

**Objective:** Show punter "Brazil's xG this match (1.8) is +0.3 above their season average — they're overperforming". Uses FixtureArchive league-season averages we just started harvesting.

**Files:**
- Create: `backend/api/routes/live.py` add `/live/match/{id}/team-context` returning per-team season averages from FixtureArchive
- Create: `frontend/components/live/StatVsSeasonBar.tsx`
- Modify: `frontend/components/live/LiveHub.tsx` LiveMatchCard adds a "vs season avg" section below the existing stat row

Note: this only renders when we HAVE >=10 season fixtures harvested for the team. WC2026 teams play 3 group games — we won't have meaningful FA data for them yet. Goal here is to show the BEAUTIFUL version we'll have once a EPL/Bundesliga side appears in a friendly (or for the round of 16+ matches against teams we have league data for). Gated with `if (avgData?.sample_size >= 10)`.

### Task 4.4: Per-card "key player face stack"

**Objective:** Show 3 face circles per team — top scorer, top assister, danger man (most goals + assists this comp). Quick visual identifier of "who matters".

**Files:**
- Modify: `backend/api/routes/live.py` enrich `/live/hub/enriched` per-match payload with `key_players: { home: [...], away: [...] }` (query PlayerProfile + PlayerTournamentStats by team_id, top 3 by goals+assists, cap to those with goals>0 OR assists>0).
- Modify: `frontend/components/live/LiveHub.tsx` LiveMatchCard renders face stack below event ticker.

### Task 4.5: Goal flash animation

**Objective:** When the score on a card changes (delta detected by client comparison vs previous tick), pulse a green ring around the card for 4 seconds + browser notification (already have NotificationBell scaffold; reuse).

**Files:**
- Modify: `frontend/components/live/LiveHub.tsx` `LiveMatchCard` — useRef on `(home_score, away_score)` previous, useEffect to detect change, set local `flashing: boolean` state for 4s with CSS animation. Also call `new Notification(...)` if permission granted.

**Verification:** Manually bump a score in dev DB (`UPDATE matches SET home_score = home_score + 1 WHERE id = '...'`), watch /live page in another tab → expect the card to pulse green + notification fires.

### Task 4.6: Push wave 4 + Playwright + dogfood

Push, Playwright visits `/live` and asserts:
- `MatchOfMoment` hero renders when `live_count > 0`
- Key-player face stack present in LiveMatchCard (img tags with alt = player name)
- Goal flash CSS class registered (visual regression hard to script — manual sanity check)

---

## Wave 5 — Tie-it-all-together surfaces

### Task 5.1: Homepage "Today's storylines" strip

A 3-card horizontally-scrolling strip ABOVE the matchday filter on `/`:
- Today's biggest upset (lowest p_win team that's currently leading or has won)
- Today's golden boot mover (player who scored multiple in the day's matches)
- Today's value pick (highest-edge market across today's matches, from existing /betting/value)

Pure aggregation, no new data. Hidden on days with no matches.

### Task 5.2: Match detail page — H2H widget

Pull from existing `/extras/matches/{matchId}/h2h` endpoint (already exposed via `api.h2h`). Add a "Last 5 meetings" section to `/match/[id]/page.tsx` showing each prior meeting with score + clickable. Visual: stacked rows + a tiny outcome dot.

### Task 5.3: Site-wide footer "Latest from your follows" (if NotificationBell user has subscribed teams)

Skip for now — needs auth/profile. Park for later.

### Task 5.4: `/players` index — top 50 scorers across leagues

Pulls PlayerTournamentStats ordered by goals desc. One-page leaderboard with photos. Surfaces the harvest data even before WC kicks off — gives the SEO long tail (`Mbappe stats wc2026` etc.) something to land on.

### Task 5.5: Push wave 5 + final Playwright sweep

Sweep all 18+ public routes, assert zero console errors, screenshot homepage / live / team / player on mobile + desktop. Save to CURRENT-BACKLOG.

---

## Risks / open questions

1. **Photo CDN reliability** — api-football photo_urls (media.api-sports.io) occasionally 404. Wrap `<img>` with `onError` fallback to neutral avatar. Add to PlayerCard + player page hero.
2. **PlayerHistory is currently empty** — per the PHASE-A-HANDOFF, `/players?team=X&season=Y` doesn't return per-fixture rows. The player detail "Recent matches" section will be empty for now. Decide: drop it from the page, or queue `/fixtures/players?fixture=X` for finished WC matches (cost ~1 call per WC fixture, 32-48 calls for the whole tournament — easy). **Recommendation:** queue it during wave 3 setup; player pages light up once data flows.
3. **Live ticker overlap with iOS safe-area** — verify on iPhone notch; the 28px is fine for non-notched, may need `safe-area-inset-top` env var. Test before declaring wave 1 done.
4. **Player profile pages for non-WC teams** — if someone clicks a player from a EPL fixture archive, they hit /player/{id} for a player whose team is not a WC team. That's fine — the page just shows their club stats and not WC outlook.
5. **Stale fixture statuses** — `/live/summary` uses `Match.status.in_(["1H","2H",...])`. Verify those are the exact statuses the live poller writes. If our system uses different codes (e.g. "live"), update the IN list.

## What this does NOT change

- No model logic touched. Multi picker, dc_ratings, calibration, scoring all unmodified.
- No new dependencies (npm or pip).
- No public-repo methodology leakage. Internal docs stay in `docs/INTERNAL/`.
- No commit messages reference scrape plans, league IDs, or model internals.
- Existing 18 routes stay live throughout. Each wave only adds new routes/components or replaces a section of an existing page.

## Suggested order of operations (real-world cadence)

- **Day 1 (today):** Waves 1 + 2 ship. Live ticker visible, team pages have photos. This alone is the biggest visible jump in months.
- **Day 2:** Wave 3 ships. Player profile pages exist.
- **Day 3+:** Wave 4 ships in pieces (storylines first, then key-player face stack, then goal flash, then MatchOfMoment last because it depends on fresh sparkline data).
- **Whenever:** Wave 5 is bolt-ons, ship as time permits.

Each wave is independently shippable. If quota runs tight on a given day, stop after a wave, don't half-ship the next one.
