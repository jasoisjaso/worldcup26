# Live Page + Match Recap + Storylines Tighten-Up Plan

> **For Claude:** Execute task-by-task. Local-first, push only when a whole wave verifies. AU English, no em-dashes in copy, no methodology/league IDs in commits.

**Goal:** Eliminate the three dogfood-confirmed friction points and give every WC match a complete "what happened" recap so users never need to leave the site to know who scored, when, possession, cards, corners, or shots.

**Architecture:** All existing data — no new API quota. Match recap reads `MatchEvent` + `MatchStatistics` + `MatchLineup` + `MatchLineupPlayer` (all populated by the live poller). Live page declutters by stacking less-used panels behind an "Expand" toggle and prioritising the bet-worthy chrome.

**Tech Stack:** Next 15 App Router · FastAPI · existing SQLAlchemy models · existing emerald/amber/slate-charcoal brand. Zero new dependencies.

---

## Research base: how the leaders do it (what we steal, what we leave)

The user explicitly said "don't copy" — use as a reference, not a template. Here's what to take and what to skip from each.

### FotMob (the gold standard for casual UX)
- **Take:** Per-team score on its OWN row (we have this now). Goal-scorer chip inline with score (e.g. "M. Cunha 23', 24', 36'"). Yellow/red card icons on player rows in the lineup. "Match facts" tiles right above the lineup. Pre-match form mini-strip per team.
- **Take:** "Top performer" or "Man of the Match" auto-pick driven by goals + assists + xG involvement. They show a single highlighted player card.
- **Leave:** Their heatmaps / pass-network / shot-map require event-level coordinates we don't have (api-football events don't include x/y). Skip these.
- **Leave:** Sponsored news pane.

### SofaScore (deepest stats)
- **Take:** Comparison bars (we have this). The "Match momentum" wave (we have sparkline). Tabbed sections: Lineups · Stats · Events · H2H · Standings. Lets you skim sections.
- **Take:** Goal flash + 2-second toast banner per goal.
- **Leave:** Heatmap, possession-by-zone, shot map (same coord problem as FotMob).
- **Leave:** Their tier-1 "PRO" gating UI patterns — we want every section visible.

### OneFootball
- **Take:** Pre-kickoff vs full-time score timeline ("kickoff Brazil 65% → FT Brazil 95%"). We already have this as our "Model shift" line. Make it a bigger feature on completed matches.
- **Leave:** Their video-thumbnail wall (we don't host video).

### Common patterns across all three (must-have)
1. Score in big monospace numerals at the top, team name + flag on each side
2. Status badge (LIVE / FT / HT / AET / PEN) prominent
3. Goal events visible WITHOUT scrolling
4. "Stats" block ALWAYS shows possession + shots + cards + corners — the minimum-viable recap
5. Lineups as a tab/section that's collapsible (lots of vertical space)
6. Coverage of the user's full mental loop: "who scored?" → "how did each team play?" → "what's our prediction now/was it right?"

### What we have that FotMob/SofaScore DON'T
- Live in-play win probability (their numbers freeze at kickoff like api-football)
- Public model track record + calibration (transparency moat)
- Bet builder with proper SGM correlation
- Closing-line value capture

**Strategy:** match-or-exceed them on the basic UX (which they win on today). Compete on the model-transparency angle (which is uniquely ours). The user said "don't have to hunt around the site" — every match-related fact in ONE place.

---

## Wave 1 — Critical bug fixes (10 minutes total)

### Task 1.1: Coming-up rows missing away flag

**Objective:** Two flags per row, not just home.

**Files:**
- Modify: `frontend/components/live/LiveHub.tsx` around line 193-196

**Current (broken):**
```tsx
const renderRow = (m: typeof upcoming.matches[number]) => (
  <Link key={m.id} href={`/match/${m.id}`} className="...">
    {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
    <span className="text-[12px] text-slate-200 font-medium truncate flex-1">{m.home_name} v {m.away_name}</span>
    <span className="text-[11px] font-mono text-slate-500 tabular-nums shrink-0">{localKickoff(m.kickoff)}</span>
  </Link>
)
```

**Fixed:**
```tsx
const renderRow = (m: typeof upcoming.matches[number]) => (
  <Link key={m.id} href={`/match/${m.id}`} className="flex items-center gap-2 px-4 py-2.5 hover:bg-surface-1 transition-colors">
    <div className="flex items-center gap-1 shrink-0">
      {m.home_flag && <img src={m.home_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
      {m.away_flag && <img src={m.away_flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover" />}
    </div>
    <span className="text-[12px] text-slate-200 font-medium truncate flex-1">{m.home_name} v {m.away_name}</span>
    <span className="text-[11px] font-mono text-slate-500 tabular-nums shrink-0">{localKickoff(m.kickoff)}</span>
  </Link>
)
```

**Verify:** visit `/live`, see both flags side-by-side on Coming up rows.

**Commit:** `git commit -m "live: coming-up rows show both team flags"`

### Task 1.2: Storylines must prefer TODAY's matches

**Objective:** If any matches finished today (UTC), show today's. Only fall back to last-36h when today is empty.

**Files:**
- Modify: `backend/api/routes/live.py` storylines function

**Change:** add a today-first preference. Pseudocode:

```python
today_utc = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
today_finished = [m for m in finished if m.kickoff and m.kickoff >= today_utc]
# Prefer today; fall back to the 36h window only if today is empty
pool = today_finished if today_finished else finished
```

Then run the upset / goalfest / player-haul detection against `pool` instead of `finished`. Add a small flag in the output:

```python
return {"cards": cards, "window": "today" if today_finished else "recent"}
```

Front-end shows "Today on the pitch" (existing copy) when window=today, "Recently on the pitch" when window=recent. Same component, just swap the label.

**Verify:** When Brazil-Haiti finishes today, the goalfest/player-haul cards switch to today's drama; Canada-Qatar from yesterday drops off.

**Commit:** `git commit -m "storylines: prefer same-UTC-day matches, fall back to 36h"`

### Task 1.3: Storylines label switches with window

**Files:**
- Modify: `frontend/components/home/StorylinesStrip.tsx`
- Modify: `frontend/lib/api.ts` — add `window` to types
- Modify: `frontend/app/page.tsx` — pass `window` through

Cosmetic label swap: header reads "Today on the pitch" when `window === "today"`, "Recently on the pitch" otherwise.

**Verify:** Refresh homepage in the morning before any matches, label reads "Recently"; after first FT today, label switches to "Today".

**Commit:** `git commit -m "storylines: label reflects today vs recent window"`

---

## Wave 2 — Match Recap module (the big one)

**Why this is the biggest win:** the user explicitly called out "doesn't even give me any actual match stats that happened when I go in there like there's 6 goals no idea who scored what the possesion was corners fouls red cards yellows". When users click into a completed match they should see EVERYTHING. Right now `/match/[id]/page.tsx` only shows the model prediction, not what actually happened.

### Task 2.1: New endpoint `/matches/{id}/recap`

**Objective:** One JSON payload with everything a recap needs.

**Files:**
- Create: `backend/api/routes/match_recap.py`
- Modify: `backend/api/main.py` to register router

**Endpoint behavior:** returns goals + cards + lineups + match stats + result. Pure DB read; no API cost.

```python
"""Per-match recap — everything a user wants to know AFTER a match finishes.
Pulled from MatchEvent + MatchStatistics + MatchLineup + MatchLineupPlayer.
Zero API cost — all written by the live poller during the match."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import (
    Match, MatchEvent, MatchStatistics, MatchLineup, MatchLineupPlayer, Team,
)
from backend.data.fetchers.injuries import TEAM_IDS

router = APIRouter()


def _team_api_id(code: str) -> int | None:
    return TEAM_IDS.get(code.lower()) if code else None


@router.get("/{match_id}/recap")
def match_recap(match_id: str, db: Session = Depends(get_db)):
    m = db.query(Match).filter(Match.id == match_id).first()
    if not m:
        raise HTTPException(404, "match not found")

    home = db.query(Team).filter(Team.code == m.home_code).first()
    away = db.query(Team).filter(Team.code == m.away_code).first()
    home_api = _team_api_id(m.home_code) if m.home_code else None
    away_api = _team_api_id(m.away_code) if m.away_code else None

    # Events: goals + cards + subs ordered by minute. Each event tagged with
    # "home" or "away" via team_id resolution.
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match_id)
        .order_by(MatchEvent.elapsed.asc(), MatchEvent.id.asc())
        .all()
    )

    def side_of(team_id):
        if team_id == home_api: return "home"
        if team_id == away_api: return "away"
        return None

    events_out = [
        {
            "minute": e.elapsed + (e.extra or 0),
            "elapsed": e.elapsed,
            "extra": e.extra,
            "type": e.type,
            "detail": e.detail,
            "player_id": e.player_id,
            "player_name": e.player_name,
            "assist_name": e.assist_name,
            "team_side": side_of(e.team_id),
            "team_name": e.team_name,
        }
        for e in events
    ]

    # Stats: latest row per team (live poller updates in-place).
    def stats_for(team_api):
        s = (
            db.query(MatchStatistics)
            .filter(MatchStatistics.match_id == match_id)
            .filter(MatchStatistics.team_id == team_api)
            .first()
        )
        if not s:
            return None
        return {
            "possession_pct": s.ball_possession,
            "shots_total": s.total_shots,
            "shots_on_target": s.shots_on_goal,
            "shots_off_target": s.shots_off_goal,
            "shots_blocked": s.blocked_shots,
            "shots_inside_box": s.shots_inside_box,
            "shots_outside_box": s.shots_outside_box,
            "corners": s.corner_kicks,
            "fouls": s.fouls,
            "offsides": s.offsides,
            "yellow_cards": s.yellow_cards,
            "red_cards": s.red_cards,
            "saves": s.goalkeeper_saves,
            "passes_total": s.total_passes,
            "passes_accurate": s.passes_accurate,
            "passes_pct": s.passes_pct,
            "xg": s.expected_goals,
        }

    # Lineups + bench
    def lineup_for(team_api):
        lu = (
            db.query(MatchLineup)
            .filter(MatchLineup.match_id == match_id)
            .filter(MatchLineup.team_id == team_api)
            .first()
        )
        if not lu:
            return None
        players = (
            db.query(MatchLineupPlayer)
            .filter(MatchLineupPlayer.lineup_id == lu.id)
            .order_by(MatchLineupPlayer.is_starter.desc(), MatchLineupPlayer.grid.asc())
            .all()
        )
        return {
            "formation": lu.formation,
            "coach": lu.coach_name,
            "starters": [
                {"player_id": p.player_id, "player_name": p.player_name, "number": p.number, "position": p.position, "grid": p.grid}
                for p in players if p.is_starter
            ],
            "bench": [
                {"player_id": p.player_id, "player_name": p.player_name, "number": p.number, "position": p.position}
                for p in players if not p.is_starter
            ],
        }

    # Man of the match: most goals + most assists. Simple heuristic; refine later.
    goal_counts = {}
    assist_counts = {}
    for e in events:
        if e.type == "Goal" and e.player_name:
            goal_counts[(e.player_name, e.player_id, side_of(e.team_id))] = goal_counts.get((e.player_name, e.player_id, side_of(e.team_id)), 0) + 1
            if e.assist_name:
                assist_counts[e.assist_name] = assist_counts.get(e.assist_name, 0) + 1
    motm = None
    if goal_counts:
        (name, pid, side), goals = max(goal_counts.items(), key=lambda x: (x[1], assist_counts.get(x[0][0], 0)))
        motm = {"player_id": pid, "name": name, "goals": goals, "side": side}

    return {
        "match_id": match_id,
        "status": m.status,
        "is_complete": m.status == "complete",
        "score": {
            "home": m.home_score,
            "away": m.away_score,
        } if m.home_score is not None else None,
        "kickoff": m.kickoff.isoformat() if m.kickoff else None,
        "venue": m.venue,
        "home": {
            "code": m.home_code,
            "name": home.name if home else (m.home_code or "").upper(),
            "flag_url": home.flag_url if home else None,
            "stats": stats_for(home_api),
            "lineup": lineup_for(home_api),
        },
        "away": {
            "code": m.away_code,
            "name": away.name if away else (m.away_code or "").upper(),
            "flag_url": away.flag_url if away else None,
            "stats": stats_for(away_api),
            "lineup": lineup_for(away_api),
        },
        "events": events_out,
        "motm": motm,
    }
```

Register in `backend/api/main.py`:
```python
from backend.api.routes import match_recap
app.include_router(match_recap.router, prefix="/matches")
```

**Verify locally:** start backend, hit `http://localhost:8000/matches/M027/recap | python -m json.tool`. Expect events array with the 6 Canada goals, stats blocks, lineups (if MatchLineup populated).

**Commit:** `git commit -m "api: match recap endpoint joining events + stats + lineups"`

### Task 2.2: `api.matchRecap()` helper

**Files:**
- Modify: `frontend/lib/api.ts`

```ts
matchRecap: (id: string) => get<{
  match_id: string;
  status: string;
  is_complete: boolean;
  score: { home: number | null; away: number | null } | null;
  kickoff: string | null;
  venue: string | null;
  home: TeamRecap;
  away: TeamRecap;
  events: RecapEvent[];
  motm: { player_id: number | null; name: string; goals: number; side: "home" | "away" } | null;
}>(`/matches/${id}/recap`),
```

Define types `TeamRecap`, `RecapEvent` next to the function.

**Commit:** `git commit -m "api: matchRecap helper"`

### Task 2.3: `MatchRecap` component (the meat)

**Objective:** A single component renders ALL the post-match content. Sections (in order):
1. **Goals timeline** — minute-by-minute list with side flag + scorer + assist (if any)
2. **Cards summary** — chips: "🟨 2 · 🟥 0" per team
3. **Stats comparison** — re-use the `StatBar` pattern from LiveHub. Possession, shots, on target, corners, fouls, offsides, yellows, reds, saves, pass accuracy.
4. **Man of the match** — auto-picked, big card with photo from PlayerProfile join
5. **Lineups** — formation string + grid layout when MatchLineup has data; collapsed by default
6. **Model trend** — "Pre-kickoff: X% Brazil → FT: 95% Brazil" using LiveWpHistory first + last tick

**Files:**
- Create: `frontend/components/match/MatchRecap.tsx`

Skeleton (each section is its own sub-component, kept in the same file for now):

```tsx
import Link from "next/link"
import type { ReactNode } from "react"

interface Stats {
  possession_pct: number | null
  shots_total: number | null
  shots_on_target: number | null
  shots_off_target: number | null
  corners: number | null
  fouls: number | null
  offsides: number | null
  yellow_cards: number | null
  red_cards: number | null
  saves: number | null
  passes_pct: number | null
  xg: number | null
}

interface TeamRecap {
  code: string | null
  name: string
  flag_url: string | null
  stats: Stats | null
  lineup: {
    formation: string | null
    coach: string | null
    starters: Array<{ player_id: number | null; player_name: string; number: number | null; position: string | null }>
    bench: Array<{ player_id: number | null; player_name: string; number: number | null; position: string | null }>
  } | null
}

interface RecapEvent {
  minute: number
  type: string
  detail: string
  player_name: string | null
  assist_name: string | null
  team_side: "home" | "away" | null
}

interface Props {
  recap: {
    is_complete: boolean
    score: { home: number | null; away: number | null } | null
    home: TeamRecap
    away: TeamRecap
    events: RecapEvent[]
    motm: { player_id: number | null; name: string; goals: number; side: "home" | "away" } | null
  }
}

// 6 sections rendered in sequence. Each one self-handles its empty state — if
// MatchStatistics is missing we just don't render that section.
export function MatchRecap({ recap }: Props) {
  return (
    <div className="space-y-5">
      <GoalsTimeline events={recap.events} home={recap.home} away={recap.away} />
      <CardSummary events={recap.events} home={recap.home} away={recap.away} />
      <StatsCompare home={recap.home.stats} away={recap.away.stats} />
      {recap.motm && <MotmCard motm={recap.motm} home={recap.home} away={recap.away} />}
      {(recap.home.lineup || recap.away.lineup) && (
        <LineupsBlock home={recap.home} away={recap.away} />
      )}
    </div>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4">
      <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-slate-500 mb-3">{title}</p>
      {children}
    </div>
  )
}

function GoalsTimeline({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  const goals = events.filter((e) => e.type === "Goal" && e.detail !== "Own Goal")
  if (goals.length === 0) {
    return <Section title="Goals">{<p className="text-[12px] text-slate-600">No goals scored.</p>}</Section>
  }
  return (
    <Section title={`Goals (${goals.length})`}>
      <div className="space-y-2">
        {goals.map((g, i) => {
          const isHome = g.team_side === "home"
          const flag = isHome ? home.flag_url : away.flag_url
          const label = isHome ? home.name : away.name
          return (
            <div key={i} className="flex items-center gap-3 text-[12.5px]">
              <span className="font-mono tabular-nums text-slate-500 w-12 shrink-0">{g.minute}'</span>
              {flag && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={flag} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
              )}
              <div className="flex-1 min-w-0">
                <p className="text-slate-100 font-semibold truncate">{g.player_name}</p>
                {g.assist_name && (
                  <p className="text-[10px] text-slate-500 truncate">assist: {g.assist_name}</p>
                )}
              </div>
              <span className="text-[10px] text-slate-600 shrink-0">{label}</span>
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function CardSummary({ events, home, away }: { events: RecapEvent[]; home: TeamRecap; away: TeamRecap }) {
  const count = (side: "home" | "away", needle: string) =>
    events.filter((e) => e.type === "Card" && e.team_side === side && (e.detail || "").includes(needle)).length
  const homeY = count("home", "Yellow")
  const homeR = count("home", "Red")
  const awayY = count("away", "Yellow")
  const awayR = count("away", "Red")
  if (homeY + homeR + awayY + awayR === 0) return null
  return (
    <Section title="Cards">
      <div className="grid grid-cols-2 gap-3 text-[12px]">
        {[["home", home, homeY, homeR], ["away", away, awayY, awayR]].map((row, i) => {
          const [side, team, y, r] = row as [string, TeamRecap, number, number]
          return (
            <div key={i} className="flex items-center gap-2">
              {team.flag_url && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={team.flag_url} alt="" className="w-5 h-3.5 rounded-[2px] object-cover shrink-0" />
              )}
              <span className="flex-1 truncate text-slate-300">{team.name}</span>
              {y > 0 && <span className="font-mono tabular-nums text-amber-300">🟨 {y}</span>}
              {r > 0 && <span className="font-mono tabular-nums text-rose-400">🟥 {r}</span>}
            </div>
          )
        })}
      </div>
    </Section>
  )
}

function Bar({ label, home, away, format = "int" }: { label: string; home: number | null; away: number | null; format?: "int" | "float" | "pct" }) {
  if (home == null && away == null) return null
  const h = home ?? 0, a = away ?? 0
  const total = h + a
  const hPct = total > 0 ? (h / total) * 100 : 50
  const fmt = (v: number | null) => {
    if (v == null) return "-"
    if (format === "float") return v.toFixed(2)
    if (format === "pct") return `${Math.round(v)}%`
    return String(Math.round(v))
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-[11px] font-mono tabular-nums">
        <span className={h > a ? "text-white font-bold" : "text-slate-400"}>{fmt(home)}</span>
        <span className="text-[9px] text-slate-600 uppercase tracking-wider font-sans">{label}</span>
        <span className={a > h ? "text-white font-bold" : "text-slate-400"}>{fmt(away)}</span>
      </div>
      <div className="flex h-1 rounded-full bg-slate-800 overflow-hidden">
        <div className="bg-emerald-500/70" style={{ width: `${hPct}%` }} />
        <div className="bg-orange-500/70" style={{ width: `${100 - hPct}%` }} />
      </div>
    </div>
  )
}

function StatsCompare({ home, away }: { home: Stats | null; away: Stats | null }) {
  if (!home && !away) return null
  return (
    <Section title="Match stats">
      <div className="space-y-2.5">
        <Bar label="Possession" home={home?.possession_pct ?? null} away={away?.possession_pct ?? null} format="pct" />
        <Bar label="Shots" home={home?.shots_total ?? null} away={away?.shots_total ?? null} />
        <Bar label="Shots on target" home={home?.shots_on_target ?? null} away={away?.shots_on_target ?? null} />
        {(home?.xg != null || away?.xg != null) && (
          <Bar label="Expected goals" home={home?.xg ?? null} away={away?.xg ?? null} format="float" />
        )}
        <Bar label="Corners" home={home?.corners ?? null} away={away?.corners ?? null} />
        <Bar label="Fouls" home={home?.fouls ?? null} away={away?.fouls ?? null} />
        <Bar label="Offsides" home={home?.offsides ?? null} away={away?.offsides ?? null} />
        <Bar label="Saves" home={home?.saves ?? null} away={away?.saves ?? null} />
        <Bar label="Pass accuracy" home={home?.passes_pct ?? null} away={away?.passes_pct ?? null} format="pct" />
      </div>
    </Section>
  )
}

function MotmCard({ motm, home, away }: { motm: NonNullable<Props["recap"]["motm"]>; home: TeamRecap; away: TeamRecap }) {
  const team = motm.side === "home" ? home : away
  return (
    <Section title="Top performer">
      <Link
        href={motm.player_id ? `/player/${motm.player_id}` : "#"}
        className="flex items-center gap-3 group"
      >
        <span className="w-12 h-12 rounded-full bg-gradient-to-br from-amber-500/30 to-amber-700/10 ring-2 ring-amber-500/30 flex items-center justify-center text-amber-300 font-black text-[16px]">
          {motm.name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase()}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-[14px] font-bold text-white truncate group-hover:text-amber-300 transition-colors">{motm.name}</p>
          <p className="text-[11px] text-slate-500">
            {team.name} · {motm.goals} {motm.goals === 1 ? "goal" : "goals"}
          </p>
        </div>
      </Link>
    </Section>
  )
}

function LineupsBlock({ home, away }: { home: TeamRecap; away: TeamRecap }) {
  return (
    <Section title="Starting lineups">
      <div className="grid grid-cols-2 gap-4 text-[11px]">
        {[home, away].map((team, i) => (
          <div key={i}>
            <p className="text-[10px] font-bold text-slate-300 mb-1.5 truncate">{team.name}{team.lineup?.formation ? ` · ${team.lineup.formation}` : ""}</p>
            {team.lineup?.starters?.length ? (
              <ul className="space-y-1">
                {team.lineup.starters.map((p) => (
                  <li key={p.player_id ?? p.player_name} className="flex items-center gap-2 text-slate-400">
                    {p.number != null && <span className="text-slate-600 font-mono w-5 text-right">{p.number}</span>}
                    {p.player_id ? (
                      <Link href={`/player/${p.player_id}`} className="truncate hover:text-emerald-300">{p.player_name}</Link>
                    ) : <span className="truncate">{p.player_name}</span>}
                  </li>
                ))}
              </ul>
            ) : <p className="text-slate-600 text-[10px]">Lineup not available.</p>}
          </div>
        ))}
      </div>
    </Section>
  )
}
```

**Verify locally:** import in /match/M027 page, render below the hero, check that goals (6 from Canada-Qatar) all show with correct flag/team mapping.

**Commit:** `git commit -m "match: recap component (goals, cards, stats bars, MOTM, lineups)"`

### Task 2.4: Wire `MatchRecap` into the match detail page

**Files:**
- Modify: `frontend/app/match/[id]/page.tsx`

**Steps:**
1. Add `matchRecap` to the `Promise.all` block.
2. Insert `<MatchRecap recap={recap} />` between the hero section (lines 117-160) and the H2H block (line 164).
3. Only render when `complete` is true OR when there are events to show.

**Verify:** visit `/match/M027` (Canada 6-0 Qatar), see all 6 goals listed with timestamps, stats bars showing possession etc.

**Commit:** `git commit -m "match: render recap section on completed matches"`

---

## Wave 3 — Live page declutter

**Why:** the user said "still don't think that live is quiet there's been some improvements". Cards are still busy. Apply visual hierarchy.

### Task 3.1: Collapse less-essential panels behind a "More" toggle

**Files:**
- Modify: `frontend/components/live/LiveHub.tsx` `LiveMatchCard`

**Always visible (the must-see):**
- Header (teams + scores + LIVE pill)
- Event ticker
- Win probability + sparkline
- Score + minute

**Collapsed behind "More" tap (less-essential):**
- Key player face stacks
- Match stats panel
- Model shift line
- Swing narrative

The card defaults to compact mode. "Show more" expands the rest. The Fun/Bet toggle stays.

This addresses the "quiet" feedback directly — the user wants signal-to-noise high by default. Power users tap "More" if they want depth.

### Task 3.2: Show MOTM live (as soon as someone has scored 2+)

**Files:**
- Modify: `backend/api/routes/live_enriched.py` to add `motm` field per live match
- Modify: `frontend/components/live/LiveHub.tsx` to render a compact MOTM chip when present

A live MOTM chip "⭐ M. Cunha · 3 goals" is way more compelling than the current key-player stack for matches with action.

---

## Wave 4 — Cross-page consistency

### Task 4.1: Live card "Full detail" link uses /match/[id] which now has the recap

Already works (Wave 2 added the recap to that page). Just confirm clicking "Full detail" on a live card gets you to the recap mid-match — `/match/{id}` shows recap when events exist even pre-FT.

### Task 4.2: Storylines "Player of the day" → /player/{id} already correct

Confirm and Playwright check.

---

## Risks / open questions

1. **MatchLineup may be empty for many matches.** api-football publishes it ~60 min pre-kickoff but only when team news lands. We harvest via the live poller. For Brazil-Haiti today, lineup might exist; for Canada-Qatar from 2 days ago, depends on whether the poller caught it. The `LineupsBlock` self-handles empty by showing "Lineup not available" — no crash, just less content.

2. **MOTM heuristic is naive.** Goals + assists only. A goalkeeper who saved a penalty doesn't get noticed. Phase 2 could weight defensive contributions when player ratings land via /fixtures/players harvest. For now: simple = good.

3. **Live page declutter might HIDE features power users use.** The Fun/Bet toggle, the model-shift narrative, the key player stack. Mitigation: "Show more" remembers state per match (sessionStorage) so a user who expands once stays expanded across polls.

4. **"Today" timezone edge:** UTC midnight vs Brisbane midnight. Currently using UTC for the today_finished filter. A match at 23:00 UTC will count as "today" for ~10am AEST viewers. Acceptable — but document it.

5. **The Cards Summary may show zeros and look empty.** Suppress the section entirely when totals are 0 on both sides (already done in the spec).

---

## What this does NOT touch

- No model/prediction logic
- No new dependencies (npm or pip)
- No quota budget changes — pure DB reads everywhere
- No public-repo methodology leaks — all commits are UI/UX framed
- No live poller changes — recap reads what's already there

## Cadence

- **Wave 1** (bug fixes): ship together in one push. ~15 min.
- **Wave 2** (match recap): one push when all 4 tasks pass locally + Playwright. ~90 min.
- **Wave 3** (declutter): independent, can ship same session as Wave 2 or next session. ~45 min.
- **Wave 4** (consistency): bolt-on at the end. ~10 min.

Total ≈ 2.5 hours of execution if all goes well.

## Plan complete and saved.

Path: `.hermes/plans/2026-06-20_030000-live-page-match-recap-research.md`

Ready to execute when the user gives the go — recommend starting Wave 1 (10 min, fixes the two visible bugs the user just called out), then Wave 2 (the big match-recap module — the single highest-value change for "don't make me hunt for info").
