# Match-page overhaul + pre-match context + group-table bugfix

> **For Hermes:** Use `subagent-driven-development` skill to execute task-by-task. Each task is sized for 2-5 min of focused work with explicit verification.

**Goal:** Fix the navigation friction + missing pre-match context inside `/match/[id]` so the user can decide a bet without leaving the match page, and fix the group-table click-through bug that says "could not load team data".

**Architecture:** Mostly composition — add 3 new components inside `frontend/components/match/`, wire 1 new backend endpoint, fix 1 proxy route. The model upgrade (Phase 4) is staged separately because it's days of work, not minutes.

**Tech Stack:** Next.js 14 App Router, FastAPI, hand-rolled SVG (no chart libs), Tailwind dark + emerald + amber tokens.

---

## Issue map (user complaints → exact code locations)

| User complaint | File / location | Fix complexity |
|---|---|---|
| Scroll-to-top when leaving a match back to MD3 tab | `frontend/app/page.tsx` matchday tabs (server-rendered, no scroll restoration) | small (Link `scroll={false}` + sessionStorage anchor) |
| Match card shows betting but no pre-match context (stakes, form, suspensions) | `frontend/app/match/[id]/page.tsx` lines 130-210 | medium (new `PreMatchBrief` component + suspensions module already exists) |
| Can't tap team names inside match detail page | `frontend/app/match/[id]/page.tsx` lines 151-178 (Flag + p, not wrapped in Link) | trivial (wrap in `<Link href={/team/[code]}>`) |
| Group-table click → "could not load team data" | `frontend/app/api/proxy/teams/[code]/route.ts` swallows backend errors → `TeamDrawer.tsx:90` triggers the error message | small (proxy needs `res.ok` check + better error envelope) |
| No best-odds / suggested picks / multi-builder inside match card | `frontend/app/match/[id]/page.tsx` already shows `MarketGrid` + `MarketsSheet`, missing the call-to-action panel | medium (new `MatchBettingPanel` summarising + linking to `/acca?prefill=<matchId>`) |
| Model rated "C" — not learning from past matches' suspensions / lineups | `backend/data/fetchers/suspensions.py` already pulls — but model multipliers aren't actively visualised, and harvested `/fixtures/statistics` blobs aren't yet wired into the lambda calibration | large (separate phase; spec written below, do not start before Phases 1-3 ship) |

---

## Phase 1: Quick UX wins (~1.5h total)

### Task 1.1: Make team names tappable on match detail page

**Objective:** Wrap the home/away team panels in `<Link href="/team/{code}">` so the user can drill into a team profile directly from the match.

**Files:**
- Modify: `frontend/app/match/[id]/page.tsx` (lines ~151-178, the two `<div className="text-center">` blocks for home and away)

**Step 1: Write component-level visual test**

We don't have a frontend test rig — instead, write an instruction for manual verification at the end of the task. Skip the failing-test step here.

**Step 2: Wrap home team panel**

Find this block (around line 151):
```tsx
<div className="text-center">
  <Flag url={match.home.flag_url} color={match.home.primary_color} />
  <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight">{match.home.name}</p>
  {prediction && <p className="text-[26px] font-black text-emerald-400 tabular-nums leading-none mt-1">{Math.round(prediction.home_win * 100)}%</p>}
</div>
```

Replace with:
```tsx
<Link
  href={`/team/${match.home.code}?from=${encodeURIComponent(`/match/${params.id}`)}`}
  className="text-center block hover:opacity-80 transition-opacity"
>
  <Flag url={match.home.flag_url} color={match.home.primary_color} />
  <p className="text-[16px] sm:text-[18px] font-bold text-slate-100 mt-2 leading-tight">{match.home.name}</p>
  {prediction && <p className="text-[26px] font-black text-emerald-400 tabular-nums leading-none mt-1">{Math.round(prediction.home_win * 100)}%</p>}
</Link>
```

**Step 3: Do the same for the away team block** (the parallel `<div className="text-center">` for `match.away` further down — same pattern, swap `match.home` → `match.away`, emerald → orange).

**Step 4: Add `import Link from "next/link"`** at the top of the file (it should already be imported via other components; verify).

**Step 5: TypeScript check + verify**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0, no new errors.

**Step 6: Commit**

```bash
git add frontend/app/match/[id]/page.tsx
git commit -m "match page: home + away panels are Links to team profile"
```

**Step 7: Manual verification (after deploy)**

Open `https://wc26.tinjak.com/match/M001`, tap the home team flag/name → should land on `/team/{code}?from=/match/M001`. Back button should return.

---

### Task 1.2: Fix scroll-to-top on matchday tabs

**Objective:** When a user is on `/` with `?matchday=3` selected and taps a match card, then later returns, they should land back on MD3 at the scroll position they left.

**Files:**
- Modify: `frontend/app/page.tsx` (the matchday tab `<Link>` components — find them and verify they pass `?matchday=N` correctly)
- Modify: `frontend/components/match/MatchCard.tsx` (the `matchHref` builder, which already passes `from=` — verify the from param round-trips back to `/?matchday=3`)

**Step 1: Read homepage matchday tab implementation**

```bash
grep -n "matchday" frontend/app/page.tsx | head -20
```

**Step 2: Identify the tab Link**

Open `frontend/app/page.tsx`, find the tab strip (a `<nav>` or `<div>` containing `<Link href={"/?matchday=N"}>`).

**Step 3: Use a Next.js scroll anchor on tabs**

Add `scroll={false}` to each tab `Link` so clicking a tab doesn't scroll-to-top within the homepage:

```tsx
<Link href={`/?matchday=${md}`} scroll={false} className="...">
  MD {md}
</Link>
```

**Step 4: Persist + restore scroll position when navigating away → back**

In `frontend/components/match/MatchCard.tsx`, before navigating to `/match/{id}`, save the current scroll position keyed by the `from` path:

```tsx
const onCardClick = () => {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(`wc26-scroll:${from ?? "/"}`, String(window.scrollY))
  }
}
```

Pass `onClick={onCardClick}` to the outer `<Link>` of the card.

Then in `frontend/app/page.tsx` (homepage), add a tiny `<script dangerouslySetInnerHTML>` block at the end of the JSX that reads the saved scroll for the current matchday and scrolls there on mount. Or — cleaner — a small client component `ScrollRestorer` inside `frontend/components/layout/` that reads `sessionStorage` based on `usePathname()` + `useSearchParams()` and scrolls back.

**Step 5: Verify with simulated mobile**

Run: `cd frontend && npx tsc --noEmit`
Then in dev mode visit `/?matchday=3`, scroll down, tap a card, hit back → page restores scroll. (Manual.)

**Step 6: Commit**

```bash
git add frontend/app/page.tsx frontend/components/match/MatchCard.tsx frontend/components/layout/ScrollRestorer.tsx
git commit -m "homepage: scroll restoration across matchday tab + match-card round-trip"
```

---

### Task 1.3: Fix group-table "could not load team data"

**Objective:** Stop the proxy from masking backend errors as "successful" JSON that contains an `{ error: ... }` payload, and remove the 5-min stale cache so users don't see the failure for 5 minutes after a transient hiccup.

**Files:**
- Modify: `frontend/app/api/proxy/teams/[code]/route.ts`
- Inspect (no edit needed): `backend/api/routes/teams.py` → confirm the `/teams/{code}/profile` endpoint exists and handles all 48 WC codes

**Step 1: Inspect the backend endpoint**

```bash
grep -n "team_profile\|teams/.*profile\|/profile" backend/api/routes/teams.py | head
```

Confirm `/teams/{code}/profile` is defined. If not, add a stub that returns at least `{ code, name, group, flag_url }`. (Likely already there — TeamProfile responses are in production.)

**Step 2: Replace the proxy route content**

`frontend/app/api/proxy/teams/[code]/route.ts`:

```tsx
import { NextResponse } from "next/server"

const BACKEND = process.env.BACKEND_URL ?? "http://wc26-backend:8000"

export async function GET(
  _req: Request,
  { params }: { params: { code: string } }
) {
  try {
    const res = await fetch(`${BACKEND}/teams/${params.code}/profile`, {
      // Removed the 5-min revalidate — a single transient failure was getting
      // cached and showing "could not load" for the full window. Short s-maxage
      // instead (30s) so refreshes recover quickly.
      next: { revalidate: 30 },
    })
    if (!res.ok) {
      // Surface the real status so the client can show a meaningful message.
      const body = await res.text().catch(() => "")
      return NextResponse.json(
        { error: `Backend ${res.status}`, detail: body.slice(0, 200) },
        { status: res.status }
      )
    }
    const data = await res.json()
    return NextResponse.json(data)
  } catch (e: unknown) {
    return NextResponse.json(
      { error: "Proxy unreachable", detail: String(e).slice(0, 200) },
      { status: 502 }
    )
  }
}
```

**Step 3: Tighten the TeamDrawer error UI**

`frontend/components/team/TeamDrawer.tsx`:
- Replace the generic "could not load team data" message with a more useful one that includes a Retry button:

```tsx
{error && !loading && (
  <div className="text-sm text-amber-300 px-4 py-3">
    <p className="font-semibold">Couldn't load this team right now</p>
    <p className="text-xs text-slate-500 mt-1">
      The backend is unreachable. This is usually transient.
    </p>
    <button
      onClick={() => { setError(false); setLoading(true); /* refetch */ }}
      className="text-xs text-emerald-400 mt-2 underline"
    >
      Retry
    </button>
  </div>
)}
```

**Step 4: TypeScript check**

Run: `cd frontend && npx tsc --noEmit`
Expected: exit 0.

**Step 5: Commit**

```bash
git add frontend/app/api/proxy/teams/[code]/route.ts frontend/components/team/TeamDrawer.tsx
git commit -m "fix: group-table team drawer no longer silently fails on transient backend errors"
```

**Step 6: Manual verification (after deploy)**

Open `/groups`, click any team in any group → drawer opens with team data. Open dev console → no console errors. If a team is genuinely missing in backend, the drawer shows the precise reason instead of a blank "could not load".

---

## Phase 2: Pre-match context expansion (~4h)

### Task 2.1: Backend — extend `/matches/{id}` payload with pre-match context

**Objective:** Surface to the frontend the data the model is already using internally: stakes (what each team needs to advance), form (last 5 results both sides), suspensions, expected XI, key player absences.

**Files:**
- Modify: `backend/api/routes/matches.py` — add a new field `pre_match_context` to the `/matches/{id}` response
- Inspect: `backend/data/fetchers/suspensions.py`, `backend/data/fetchers/results.py`, `backend/data/fetchers/lineups.py` — pull from what's already there
- New: `backend/data/match_context.py` — pure assembler (no API calls; pulls from cached/persisted data only)

**Step 1: Write failing test**

`backend/tests/test_match_context.py`:

```python
"""Pre-match context assembler: returns stakes + form + absences for a match."""
from backend.data.match_context import build_pre_match_context

def test_returns_dict_with_required_keys():
    ctx = build_pre_match_context(match_id="M001", db=None, mock=True)
    assert "stakes" in ctx
    assert "home_form" in ctx
    assert "away_form" in ctx
    assert "home_absences" in ctx
    assert "away_absences" in ctx

def test_stakes_string_makes_grammatical_sense():
    ctx = build_pre_match_context(match_id="M001", db=None, mock=True)
    s = ctx["stakes"]
    assert isinstance(s, str)
    assert len(s) > 10
```

Run: `pytest backend/tests/test_match_context.py -v` → FAIL (module not found)

**Step 2: Implement the assembler**

`backend/data/match_context.py`:

```python
"""Pre-match context: pure DB / cache reads, no API calls.

Composes:
- stakes: what each team needs from this match (group position, advance scenarios)
- home_form / away_form: last 5 completed results (W/D/L + score)
- home_absences / away_absences: known suspensions + persisted injuries
- expected_xi: cached from /fixtures/lineups when available, else None

Idempotent and cheap — called by the /matches/{id} route on every request.
"""
from __future__ import annotations
from typing import Optional
from sqlalchemy.orm import Session

from backend.db.models import Match, Team
from backend.data.fetchers.suspensions import suspensions_for_match
from backend.data.fetchers.injuries_persist import injuries_for_team
from backend.data.fetchers.results import recent_form_for_team

def build_pre_match_context(match_id: str, db: Session, mock: bool = False) -> dict:
    if mock:
        return {
            "stakes": "Both teams need a result to keep advancement chances alive.",
            "home_form": [],
            "away_form": [],
            "home_absences": [],
            "away_absences": [],
            "expected_xi": None,
        }
    m = db.get(Match, match_id)
    if not m:
        return {
            "stakes": "",
            "home_form": [],
            "away_form": [],
            "home_absences": [],
            "away_absences": [],
            "expected_xi": None,
        }
    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)
    return {
        "stakes": _compose_stakes(m, home, away, db),
        "home_form": recent_form_for_team(home.code, db, limit=5),
        "away_form": recent_form_for_team(away.code, db, limit=5),
        "home_absences": _absences(m, home, db),
        "away_absences": _absences(m, away, db),
        "expected_xi": _expected_xi(m, db),
    }

def _compose_stakes(m, home, away, db) -> str:
    # Group-stage logic: read GroupStandings, compute "needs win / can draw / safe"
    # for each side. Keep the string short and concrete.
    if m.stage != "group":
        return f"Knockout — {home.name} vs {away.name}, winner advances."
    # ... compute from group standings ...
    return f"{home.name} vs {away.name} — group {m.group}, matchday {m.matchday}."

def _absences(m, team, db) -> list[dict]:
    susps = suspensions_for_match(m.id, team.code) or []
    injs = injuries_for_team(team.code) or []
    return [{"name": p["name"], "reason": p["reason"]} for p in (susps + injs)]

def _expected_xi(m, db) -> Optional[dict]:
    # If we have a cached /fixtures/lineups response in MatchLineup, surface it.
    # Otherwise None — UI will show "expected lineup not yet available".
    return None  # Wire to MatchLineup table in a follow-up — out of scope for this task.
```

Run: `pytest backend/tests/test_match_context.py -v` → PASS

**Step 3: Surface context in the matches route**

`backend/api/routes/matches.py`:
- Find the `GET /matches/{id}` handler.
- Add a call to `build_pre_match_context(match_id, db)`.
- Add `pre_match_context: dict` to the response model.

```python
from backend.data.match_context import build_pre_match_context
# ...
@router.get("/{match_id}")
def get_match(match_id: str, db: Session = Depends(get_db)) -> dict:
    # ... existing logic ...
    payload = {
        # ... existing fields ...
        "pre_match_context": build_pre_match_context(match_id, db),
    }
    return payload
```

**Step 4: Run all backend tests**

Run: `pytest backend/tests/ -x --ignore=backend/tests/test_backtest.py`
Expected: all pass (test_backtest needs numpy which isn't in this venv).

**Step 5: Commit**

```bash
git add backend/data/match_context.py backend/tests/test_match_context.py backend/api/routes/matches.py
git commit -m "matches: /matches/{id} now includes pre_match_context (stakes, form, absences)"
```

---

### Task 2.2: Frontend — `PreMatchBrief` component

**Objective:** Render the new `pre_match_context` payload as a tile that sits ABOVE the existing markets panel. Stakes + form chips + absences list.

**Files:**
- New: `frontend/components/match/PreMatchBrief.tsx`
- Modify: `frontend/lib/types.ts` (add `pre_match_context` to `Match` type)
- Modify: `frontend/app/match/[id]/page.tsx` (mount the component between the team header card and the markets section)

**Step 1: Extend the Match type**

`frontend/lib/types.ts`:
```ts
export interface Match {
  // ... existing fields ...
  pre_match_context?: {
    stakes: string
    home_form: { result: "W" | "D" | "L"; opponent: string; score: string }[]
    away_form: { result: "W" | "D" | "L"; opponent: string; score: string }[]
    home_absences: { name: string; reason: string }[]
    away_absences: { name: string; reason: string }[]
    expected_xi: null | { home: string[]; away: string[]; formation_home: string; formation_away: string }
  }
}
```

**Step 2: Write the component**

`frontend/components/match/PreMatchBrief.tsx`:

```tsx
import type { Match } from "@/lib/types"

interface Props {
  match: Match
}

export function PreMatchBrief({ match }: Props) {
  const ctx = match.pre_match_context
  if (!ctx) return null

  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">What's at stake</p>
      <p className="text-[13px] text-slate-200 leading-relaxed mb-4">{ctx.stakes}</p>

      <div className="grid grid-cols-2 gap-3">
        <FormColumn label={match.home.name} form={ctx.home_form} accent="emerald" />
        <FormColumn label={match.away.name} form={ctx.away_form} accent="orange" />
      </div>

      {(ctx.home_absences.length > 0 || ctx.away_absences.length > 0) && (
        <div className="grid grid-cols-2 gap-3 mt-4">
          <AbsencesColumn label={`${match.home.name} out`} list={ctx.home_absences} />
          <AbsencesColumn label={`${match.away.name} out`} list={ctx.away_absences} />
        </div>
      )}
    </section>
  )
}

function FormColumn({ label, form, accent }: { label: string; form: { result: string; opponent: string; score: string }[]; accent: "emerald" | "orange" }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label} · last 5</p>
      <div className="flex gap-1">
        {form.length === 0 && <span className="text-[11px] text-slate-600">No recent fixtures</span>}
        {form.map((r, i) => (
          <span
            key={i}
            title={`${r.result} vs ${r.opponent} (${r.score})`}
            className={`w-6 h-6 rounded text-[10px] font-bold flex items-center justify-center ${
              r.result === "W" ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/40"
              : r.result === "D" ? "bg-slate-500/20 text-slate-400 border border-slate-500/40"
              : "bg-amber-500/20 text-amber-300 border border-amber-500/40"
            }`}
          >
            {r.result}
          </span>
        ))}
      </div>
    </div>
  )
}

function AbsencesColumn({ label, list }: { label: string; list: { name: string; reason: string }[] }) {
  if (list.length === 0) return <div className="text-[11px] text-slate-600">{label}: no known absences</div>
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">{label}</p>
      <ul className="space-y-1">
        {list.map((p, i) => (
          <li key={i} className="text-[11px] text-slate-300 flex justify-between">
            <span className="truncate">{p.name}</span>
            <span className="text-slate-600 ml-2 shrink-0">{p.reason}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
```

**Step 3: Mount it on the match page**

`frontend/app/match/[id]/page.tsx`, just below the existing team-header card (around line 200, after the closing `</div>` of the score / probability block):

```tsx
<PreMatchBrief match={match} />
```

And add the import at the top:
```tsx
import { PreMatchBrief } from "@/components/match/PreMatchBrief"
```

**Step 4: TypeScript check**

Run: `cd frontend && npx tsc --noEmit` → exit 0.

**Step 5: Commit**

```bash
git add frontend/components/match/PreMatchBrief.tsx frontend/lib/types.ts frontend/app/match/[id]/page.tsx
git commit -m "match page: PreMatchBrief tile (stakes, form, absences)"
```

---

### Task 2.3: Surface model-relevant absences in the verdict text

**Objective:** When the model reads suspensions/injuries, mention them by name in the `MatchVerdict` blurb — so a user opens the page and sees "Bosnia missing 2 starters (Krunić, Pjanić) — model has cut their win % by ~6 points."

**Files:**
- Modify: `backend/api/routes/predictions.py` — surface the suspension impact in the response
- Modify: `frontend/components/match/MatchVerdict.tsx` — render the absence-driven swing

**Step 1: Backend: expose the absence-driven model delta**

In `backend/api/routes/predictions.py`, find the section where lineup/injury multipliers are applied. Wrap the call to compute a `before vs after` comparison and add to the response payload:

```python
# Existing: home_win, draw, away_win after all modifiers.
# New: compute the no-modifier baseline and report the delta from absences.
from copy import deepcopy
baseline_mods = deepcopy(ctx["modifiers"])
for key in ("lineup_multipliers", "injury_multipliers"):
    baseline_mods[key] = (1.0, 1.0)
pred_no_absences = predict_group_match(
    home_input, away_input,
    venue_context=venue_context, matchday=m.matchday,
    **baseline_mods,
)
absence_swing_home = round(pred.home_win - pred_no_absences.home_win, 4)
# Add to payload:
payload["absence_swing"] = {
    "home_pp": round(absence_swing_home * 100, 1),
    "away_pp": round(-absence_swing_home * 100, 1),  # zero-sum approx for 1X2
}
```

**Step 2: Frontend: render it in MatchVerdict**

Read existing `MatchVerdict.tsx`. Insert a small inline line below the existing model-read sentence:

```tsx
{prediction.absence_swing && (
  <p className="text-[11px] text-slate-500 mt-2">
    Suspensions / injuries shifted the model by{" "}
    {prediction.absence_swing.home_pp > 0 ? "+" : ""}{prediction.absence_swing.home_pp}pp for {match.home.name}.
  </p>
)}
```

**Step 3: TypeScript check + tests**

Run: `cd frontend && npx tsc --noEmit` → exit 0.
Run: `pytest backend/tests/test_market.py backend/tests/test_admin_auth.py` → all pass.

**Step 4: Commit**

```bash
git add backend/api/routes/predictions.py frontend/components/match/MatchVerdict.tsx frontend/lib/types.ts
git commit -m "predictions: surface absence-driven model swing in MatchVerdict"
```

---

## Phase 3: In-context betting tools (~3h)

### Task 3.1: `MatchBettingPanel` — best price + top model picks + multi nudge

**Objective:** Inside the match detail page, surface (a) the best price across books for each main market, (b) the model's top 2 EV picks for this match, (c) a "Build a multi from this match" CTA that opens `/acca?prefill={matchId}`.

**Files:**
- New: `frontend/components/match/MatchBettingPanel.tsx`
- Modify: `frontend/app/match/[id]/page.tsx` (mount component below `PreMatchBrief` and above `MarketsSheet`)
- Modify: `frontend/app/acca/page.tsx` — read `?prefill=` query param, auto-add legs from that match

**Step 1: Component**

`frontend/components/match/MatchBettingPanel.tsx`:

```tsx
"use client"
import Link from "next/link"
import { ArrowRight } from "lucide-react"
import { formatEV, evColor } from "@/lib/utils"
import type { Match, MatchPrediction } from "@/lib/types"

interface Props {
  match: Match
  prediction: MatchPrediction | null
  matchId: string
}

export function MatchBettingPanel({ match, prediction, matchId }: Props) {
  if (!prediction) return null

  const topPicks = (prediction.markets ?? [])
    .filter((m) => m.is_positive_ev)
    .sort((a, b) => b.ev - a.ev)
    .slice(0, 2)

  return (
    <section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5">
      <div className="flex items-baseline justify-between mb-3">
        <p className="text-[10px] uppercase tracking-wider text-slate-500">Your bet, in one place</p>
        <Link
          href={`/acca?prefill=${matchId}`}
          className="text-[11px] font-semibold text-emerald-400 hover:text-emerald-300 inline-flex items-center gap-1"
        >
          Build a multi <ArrowRight size={12} />
        </Link>
      </div>

      {topPicks.length === 0 && (
        <p className="text-[12px] text-slate-500">
          No model-edge picks for this match. Markets below for reference.
        </p>
      )}

      {topPicks.map((m) => (
        <div key={m.market} className="flex items-center justify-between gap-3 py-2 border-t border-edge first:border-t-0">
          <div className="min-w-0">
            <p className="text-[13px] font-semibold text-slate-100 truncate">{m.label}</p>
            <p className="text-[10px] text-slate-500">
              Model {Math.round(m.our_probability * 100)}% · Book {m.bookmaker_odds.toFixed(2)}
            </p>
          </div>
          <div className="text-right shrink-0">
            <p className={`font-mono text-[14px] font-bold ${evColor(m.ev)}`}>
              {formatEV(m.ev)}
            </p>
            <p className="text-[9px] text-slate-600 uppercase tracking-wider">model edge</p>
          </div>
        </div>
      ))}
    </section>
  )
}
```

**Step 2: Mount on match page**

`frontend/app/match/[id]/page.tsx`, below `<PreMatchBrief>` and above the existing markets section:

```tsx
<MatchBettingPanel match={match} prediction={prediction} matchId={params.id} />
```

**Step 3: Wire `/acca?prefill={matchId}`**

Read `frontend/app/acca/page.tsx`. Add a server-side fetch when `searchParams.prefill` is set to grab the markets for that match. Pass the markets to `<MultiBuilder>` as `prefillMarkets` prop. Then in `MultiBuilder.tsx`, when `prefillMarkets` is non-empty, auto-add them as starting legs.

```tsx
// frontend/app/acca/page.tsx
const prefillMatchId = searchParams.prefill
const prefillMarkets = prefillMatchId
  ? await api.markets(prefillMatchId).catch(() => null)
  : null
// ... pass to <MultiBuilder prefillMarkets={prefillMarkets} prefillMatchId={prefillMatchId} />
```

**Step 4: TypeScript check + commit**

Run: `cd frontend && npx tsc --noEmit` → exit 0.

```bash
git add frontend/components/match/MatchBettingPanel.tsx frontend/app/match/[id]/page.tsx frontend/app/acca/page.tsx frontend/components/acca/MultiBuilder.tsx
git commit -m "match page: in-context betting panel + Build-a-multi prefill from match"
```

---

## Phase 4: Model upgrade — actively use harvested data (DAYS, do not start before Phases 1-3 ship)

**Important:** This is a separate, larger workstream. Do NOT begin until Phases 1-3 are deployed and verified. Each task is sized for a half-day to a full day of careful work + backtest.

### Task 4.1: Wire harvested `/fixtures/statistics` blobs into player xG ratings

**Goal:** The harvester is already accumulating xG / shots-on-target / possession per fixture per team. Build an offline calibration pipeline that:
1. Aggregates per-player xG / xA contribution from the FixtureArchive rows
2. Produces a `player_strength_rating` table (PK player_id, value float, last_updated)
3. Surfaces this into `lineup_multipliers` so an actual model modifier exists for "Bosnia's playmaker is rated 1.08, missing him drops the lambda by 8%"

Backtest required: validate the new player ratings against held-out OOS matches BEFORE flipping the production switch.

### Task 4.2: Suspensions feed into a richer model modifier

**Goal:** Replace the current flat -40 ELO per suspension with a player-specific impact based on the new player ratings from 4.1. A suspended bench player → ~0 impact. A suspended key starter → meaningful impact.

### Task 4.3: Per-fixture player rows (the `PlayerHistory` table)

**Goal:** The `Per-fixture player rows: 0` coverage card on `/admin` is a known gap. Enable the `/fixtures/players` endpoint in the harvester (currently NOT enqueued), wire its response into `PlayerHistory`. Then re-train the player ratings from richer data.

### Task 4.4: Re-train Dixon-Coles with xG instead of goals

**Goal:** Use `xg_home / xg_away` from FixtureArchive as the input to DC fitting instead of actual goals. Should reduce variance + improve calibration. Backtest with `backend/eval/backtest.py` over the existing 1,500 OOS dataset.

---

## Files likely to change

**Phase 1:**
- `frontend/app/match/[id]/page.tsx`
- `frontend/components/match/MatchCard.tsx`
- `frontend/components/layout/ScrollRestorer.tsx` (new)
- `frontend/app/page.tsx`
- `frontend/app/api/proxy/teams/[code]/route.ts`
- `frontend/components/team/TeamDrawer.tsx`

**Phase 2:**
- `backend/data/match_context.py` (new)
- `backend/api/routes/matches.py`
- `backend/tests/test_match_context.py` (new)
- `frontend/components/match/PreMatchBrief.tsx` (new)
- `frontend/lib/types.ts`
- `backend/api/routes/predictions.py`
- `frontend/components/match/MatchVerdict.tsx`

**Phase 3:**
- `frontend/components/match/MatchBettingPanel.tsx` (new)
- `frontend/app/acca/page.tsx`
- `frontend/components/acca/MultiBuilder.tsx`

**Phase 4:** TBD per task — heavy backend + offline backtest work.

---

## Tests / validation

After each Phase:
1. `pytest backend/tests/ -x --ignore=backend/tests/test_backtest.py` → all pass
2. `cd frontend && npx tsc --noEmit` → exit 0
3. `bash scripts/smoke-test.sh` → 12/12 routes green
4. Manual: visit `/match/M001` and verify the new sections render correctly with real data

For Phase 4 specifically: backtest before deploy. Use `backend/eval/backtest.py` to confirm the new player-rating-derived multipliers don't degrade Brier / log-loss on the OOS set.

---

## Risks, tradeoffs, open questions

**Risks:**
- The `PreMatchBrief` depends on suspensions data. The suspensions feeder writes to `data/overrides/suspensions.json` via football-data.org — that key might be rate-limited or stale. If absences are systematically missing, the brief will show "no known absences" frequently and reduce its value. Mitigation: surface the data source + last-updated timestamp inline.
- The matchday scroll-restoration approach uses `sessionStorage`, which doesn't survive a hard-reload. Acceptable; it survives soft-nav (Link clicks), which is the common case.
- The `/acca?prefill=` route fetches match markets server-side which adds one backend call per acca-page visit when prefill is set. Negligible — markets are cached.

**Tradeoffs:**
- Phase 4 is intentionally NOT broken into bite-sized tasks here because the model work needs design discussion before implementation. Each task in Phase 4 is the moral equivalent of a small standalone project.

**Open questions:**
1. Should the `PreMatchBrief` ALSO show head-to-head stats? Currently the match page has a `<HeadToHead>` panel further down. Decide: dedupe vs surface both.
2. For Phase 3, the `MultiBuilder` prefill: should it select the top 2 EV markets automatically, or just open the builder with the match's markets list and let the user pick? Recommend auto-add top 2 with a "Clear" button.
3. Phase 4 task 4.4 (re-train DC with xG): operational impact is significant — the model version bumps and the public report card resets to "early sample" mode. Worth doing? Or stick with goals + use xG only for player ratings?

---

## Execution handoff

This plan is ready to execute. Recommended order:

1. **Phase 1 (today, ~1.5h)** — quick wins, ship before any harder work
2. **Phase 2 (tomorrow, ~4h)** — pre-match brief, biggest user-visible content lift
3. **Phase 3 (day 3, ~3h)** — betting panel + multi prefill
4. **Phase 4 (separate week)** — design + spec each task before implementing; require backtest sign-off before production deploy

If using subagent-driven-development: dispatch one subagent per Task (1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1) with the full task spec, run two-stage review (spec compliance + code quality), and proceed only when both pass.
