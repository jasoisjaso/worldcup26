# Comprehensive Match + Team Page Overhaul + Model Rebuild

> **For Hermes:** Use `subagent-driven-development` to execute task-by-task. This plan supersedes the earlier `2026-06-21_092000-match-page-overhaul.md` — same scope, expanded with team-page overhaul + model-rebuild based on real DB inventory.

**Goal:** Turn `/match/[id]` and `/team/[code]` into bet-decision-ready pages by surfacing the data we already harvest but don't show, then retrain the model to learn from that data.

**Why:** User flagged that match cards lack pre-match context (suspensions, stakes, form-with-opponent, H2H), team pages only show W/D/L chips without WHO they played, group-drawer clicks fail, model is rated C-grade because it doesn't actively consume the harvested xG/cards/corners/lineup data.

---

## RESEARCH FINDINGS — what we actually have

I audited the DB schema, FixtureArchive contents, existing endpoints. Here's the honest inventory.

### Data we HAVE (just not surfacing)

| Source | Columns / fields | Used today? |
|---|---|---|
| `FixtureArchive` (137 rows + growing) | `possession`, `shots_total`, `shots_on_target`, `xg`, `pass_accuracy`, `fouls`, `yellow_cards`, `red_cards`, `corners` per (fixture × team) | NO — completely unused on FE |
| `TeamSeasonStats` | `matches_played`, `wins/draws/losses`, `goals_for/against`, `xg_for/against`, `possession_avg`, `shots_*`, `clean_sheets`, `yellow/red cards` per team | NO — never rendered |
| `MatchH2H` | Last 5-10 H2H meetings + scores + competition + season + venue | YES — but the `<HeadToHead>` component lives at the BOTTOM of `/match/[id]`, low-visibility |
| `ApiFootballPrediction` | Comparison panel (form, attack, defence, H2H, Poisson, goals percentages) | YES — rendered in `model-shift` narrative but never directly comparison-tabled |
| `MatchLineup` + `MatchLineupPlayer` | Confirmed XI + formation per fixture | Rarely — only after kickoff |
| `MatchEvent` | Per-minute timeline (goals, cards, subs) | YES — match-recap module |
| Team profile endpoint (`GET /teams/{code}/profile`) returns | `code, name, flag_url, primary_color, elo, fifa_ranking, manager, set_piece_attack, set_piece_defense, squad, upcoming_fixtures` | Used by FE |
| `api.teamRecentForm` already returns | `match_id, opponent_code, score, result, kickoff, venue` per recent match | Used by `FormStrip` but **opponent name + score not actually rendered** — only colour-coded W/D/L chip |

### Data we DON'T have / can't get cheaply

| Wanted | Source | Verdict |
|---|---|---|
| Per-player season ratings (Sofascore-style 7.2 etc) | Needs `/fixtures/players` endpoint which we don't currently enqueue | Possible (requires harvester seed addition) |
| Tactical heatmap | Not in api-football | Skip |
| Pressing intensity (PPDA) | Not reliable from our feed | Skip |
| Goal-type split (open play / set piece / penalty) | `MatchEvent` has the data but not aggregated | Possible, ~half-day work |
| Live suspensions feed | `data/overrides/suspensions.json` (manually maintained + football-data.org auto-pull) | Already used by suspensions module — model HAS this, FE doesn't show it |

### Endpoints currently exposed

```
/matches/{id}                — match + prediction + h2h
/matches/{id}/markets         — 30+ market fair-odds sheet
/teams/{code}/profile         — basic profile (squad + upcoming)
/teams/{code}/recent-form     — last N results (returns opponent + score, but FormStrip only renders chip)
/teams/radar                  — percentile rank across attack/def/etc
/predictions/{id}             — full model output
```

### Endpoints we NEED to add

```
/teams/{code}/season-stats    — averages: goals/match, corners/match, cards/match, BTTS%, CS%, xG diff
/teams/{code}/match-log       — every result with opp name + score + xG diff + competition (last 10-20)
/teams/{code}/h2h-aggregate   — all-time and recent-window vs ANY opponent
/matches/{id}/pre-match-context — composite: stakes + form + absences + season-stat compare + H2H summary
```

---

## Phase 1 — Quick UX wins (carry from prior plan, ~1.5h)

### Task 1.1: Make team panels on match detail tappable

**Files:** `frontend/app/match/[id]/page.tsx:151-178`

Wrap home + away `<div className="text-center">` blocks in `<Link href={/team/{code}?from=/match/{id}}>`. Already specified in detail in the prior plan — carry verbatim.

### Task 1.2: Scroll restoration on matchday tabs

**Files:** `frontend/app/page.tsx`, `frontend/components/match/MatchCard.tsx`, new `frontend/components/layout/ScrollRestorer.tsx`

Already specified in detail in the prior plan.

### Task 1.3: Fix group-drawer "could not load team data"

**Files:** `frontend/app/api/proxy/teams/[code]/route.ts`, `frontend/components/team/TeamDrawer.tsx`

Already specified in detail in the prior plan.

### Task 1.4 (NEW): FormStrip renders opponent + score, not just W/D/L chip

**Objective:** The data is already in `api.teamRecentForm` (`opponent_code`, `score`, `venue`) — the chip throws it away. Show opponent flag + score next to the chip.

**Files:**
- Modify: `frontend/components/team/FormStrip.tsx`
- Reuse: `frontend/components/common/Flag.tsx` for the opponent flag

**Step 1: Locate FormStrip**

```bash
grep -nE "result|W\b|chip" frontend/components/team/FormStrip.tsx
```

**Step 2: Replace chip-only rendering with a row**

```tsx
{form.map((f, i) => (
  <div key={i} className="flex items-center gap-2 py-1.5 border-t border-edge first:border-t-0">
    <span className={`w-6 h-6 rounded text-[10px] font-bold flex items-center justify-center ${chipClass(f.result)}`}>
      {f.result ?? "?"}
    </span>
    <span className="text-[10px] text-slate-600 uppercase tracking-wider w-4">{f.venue}</span>
    <Flag code={f.opponent_code} cls="w-5 h-3.5 rounded ring-1 ring-white/10" />
    <span className="text-[12px] text-slate-300 flex-1 truncate">vs {f.opponent_code.toUpperCase()}</span>
    <span className="text-[12px] font-mono text-slate-200 tabular-nums">{f.score}</span>
  </div>
))}
```

**Step 3:** TypeScript check + commit.

```bash
git commit -m "FormStrip: show opponent + score next to result chip (data was already there)"
```

---

## Phase 2 — Match page intelligence (~6h)

### Task 2.1: Backend — composite `/matches/{id}/pre-match-context`

**Objective:** ONE endpoint that returns everything a user needs to decide a bet without leaving the page.

**Files:**
- New: `backend/data/match_context.py`
- New: `backend/data/team_season_aggregates.py` (rebuilds averages from `FixtureArchive`)
- Modify: `backend/api/routes/matches.py`
- New: `backend/tests/test_match_context.py`

**Payload shape:**

```python
{
  "stakes": "Bosnia need a win — a draw eliminates them with Qatar already through.",
  "home_form": [{"result": "W", "opponent": "Kyrgyzstan", "score": "3-1", "venue": "H", "xg_diff": 1.8}, ...],
  "away_form": [...],
  "home_absences": [{"name": "M. Krunić", "reason": "suspended (yellow card accumulation)"}],
  "away_absences": [...],
  "season_stats": {
    "home": {"goals_per_match": 1.7, "conceded_per_match": 0.9, "corners_per_match": 5.3, "yellow_per_match": 2.1, "btts_pct": 0.55, "cs_pct": 0.30, "xg_diff_per_match": 0.6},
    "away": {...}
  },
  "h2h_summary": {"meetings": 3, "home_wins": 2, "draws": 1, "away_wins": 0, "last": "Bosnia 2-0 Qatar (2018-09-07)", "agg_goals_per_meeting": 2.3},
  "expected_xi_known": false,
  "model_swing_from_absences": {"home_pp": -3.5, "away_pp": 1.2}
}
```

**Step 1: Failing test**

```python
from backend.data.match_context import build_pre_match_context

def test_returns_required_top_level_keys():
    ctx = build_pre_match_context("M001", db=None, mock=True)
    assert set(ctx) >= {"stakes", "home_form", "away_form", "home_absences", "away_absences",
                        "season_stats", "h2h_summary", "model_swing_from_absences"}

def test_season_stats_have_both_sides():
    ctx = build_pre_match_context("M001", db=None, mock=True)
    s = ctx["season_stats"]
    for side in ("home", "away"):
        assert side in s
        for k in ("goals_per_match", "conceded_per_match", "corners_per_match",
                  "yellow_per_match", "btts_pct", "cs_pct", "xg_diff_per_match"):
            assert k in s[side]
```

Run + see failure. Then implement.

**Step 2: Build the team-aggregates helper**

`backend/data/team_season_aggregates.py`:

```python
"""Aggregate FixtureArchive rows into per-team season averages.

Read-only: no API calls. Cheap to call per request — single SQL query per team
with a few aggregates. Caller is /matches/{id}/pre-match-context.
"""
from sqlalchemy.orm import Session
from sqlalchemy import func
from backend.db.models import FixtureArchive

def season_aggregates(team_api_id: int, db: Session, limit: int = 38) -> dict | None:
    rows = (
        db.query(FixtureArchive)
        .filter(FixtureArchive.team_api_id == team_api_id)
        .order_by(FixtureArchive.captured_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        return None
    n = len(rows)
    out = {
        "matches_sampled": n,
        "corners_per_match":   round(sum(r.corners or 0 for r in rows) / n, 1),
        "yellow_per_match":    round(sum(r.yellow_cards or 0 for r in rows) / n, 2),
        "red_per_match":       round(sum(r.red_cards or 0 for r in rows) / n, 2),
        "shots_per_match":     round(sum(r.shots_total or 0 for r in rows) / n, 1),
        "shots_on_target_per_match": round(sum(r.shots_on_target or 0 for r in rows) / n, 1),
        "xg_per_match":        round(sum(r.xg or 0 for r in rows) / n, 2),
        "possession_avg":      round(sum(r.possession or 50 for r in rows) / n, 1),
        "pass_accuracy_avg":   round(sum(r.pass_accuracy or 0 for r in rows) / n, 1),
    }
    return out
```

**Step 3: Build the context assembler** (`backend/data/match_context.py`):

Compose `stakes` (group-position logic), pull `recent_form_for_team` for both sides, `season_aggregates` for both sides (lookup team api ids via `TEAM_IDS`), pull `MatchH2H` rows for the (team1, team2) pair, sum them, return.

Compute `model_swing_from_absences` by running `predict_group_match` twice: once with the real modifiers, once with `lineup_multipliers = (1.0, 1.0)` and `injury_multipliers = (1.0, 1.0)`. Diff the home_win.

**Step 4: Wire to route**

`backend/api/routes/matches.py` — add `GET /matches/{id}/pre-match-context` returning the dict.

**Step 5: Verify tests + commit**

```bash
pytest backend/tests/test_match_context.py -v
git add backend/data/match_context.py backend/data/team_season_aggregates.py backend/api/routes/matches.py backend/tests/test_match_context.py
git commit -m "matches: /matches/{id}/pre-match-context endpoint with season stats + h2h + absences"
```

### Task 2.2: Frontend — `PreMatchBrief` rich component (replaces both old form chip area + moves H2H inline)

**Files:**
- New: `frontend/components/match/PreMatchBrief.tsx`
- Modify: `frontend/lib/types.ts` (add `PreMatchContext` type)
- Modify: `frontend/lib/api.ts` (add `api.preMatchContext(id)`)
- Modify: `frontend/app/match/[id]/page.tsx` (mount above markets; REMOVE the bottom `<HeadToHead>` block since it now lives inside the brief)

**Layout (top to bottom inside the brief):**

1. **Stakes** — short sentence
2. **Side-by-side stat comparison** (paired bars) — goals/match, corners/match, yellows/match, BTTS%, clean-sheet%, xG diff. Bars are SVG, hand-rolled, length proportional to value, the higher value coloured.
3. **Last-5 form rows** for each team — chip + venue + opponent + score (uses the same row pattern as the new FormStrip from Task 1.4)
4. **Head-to-head section** — meetings count, win record from home perspective, last meeting score + date
5. **Absences** — list per team. If empty: "no known absences" in slate-600.

This component is dense but should still feel scannable. Section dividers with `border-t border-edge`.

**Visual reference (sketch in Tailwind):**

```tsx
<section className="rounded-2xl border border-edge bg-surface-2 shadow-e1 p-4 mb-5 space-y-4">
  {/* 1) Stakes */}
  <div>
    <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-1">What's at stake</p>
    <p className="text-[13px] text-slate-200">{ctx.stakes}</p>
  </div>

  {/* 2) Stat comparison — paired bars */}
  <StatCompare home={ctx.season_stats.home} away={ctx.season_stats.away}
               homeName={match.home.name} awayName={match.away.name} />

  {/* 3) Form rows */}
  <div className="grid grid-cols-2 gap-3">
    <FormColumn label={match.home.name} form={ctx.home_form} />
    <FormColumn label={match.away.name} form={ctx.away_form} />
  </div>

  {/* 4) H2H */}
  <H2HInline summary={ctx.h2h_summary} homeName={match.home.name} awayName={match.away.name} />

  {/* 5) Absences */}
  {(ctx.home_absences.length > 0 || ctx.away_absences.length > 0) && (
    <Absences home={ctx.home_absences} away={ctx.away_absences}
              homeName={match.home.name} awayName={match.away.name} />
  )}
</section>
```

`StatCompare` component (the paired-bar pattern industry-standard from FotMob / Sofascore):

```tsx
const STATS = [
  { key: "xg_per_match", label: "xG / match", fmt: (v: number) => v.toFixed(2), higherBetter: true },
  { key: "corners_per_match", label: "Corners / match", fmt: (v: number) => v.toFixed(1), higherBetter: true },
  { key: "shots_on_target_per_match", label: "Shots on target / match", fmt: (v: number) => v.toFixed(1), higherBetter: true },
  { key: "yellow_per_match", label: "Yellows / match", fmt: (v: number) => v.toFixed(1), higherBetter: false },
  { key: "possession_avg", label: "Possession", fmt: (v: number) => `${Math.round(v)}%`, higherBetter: null },
]

function StatCompare({ home, away, homeName, awayName }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-wider text-slate-500 mb-2">Season form comparison</p>
      {STATS.map(({ key, label, fmt, higherBetter }) => {
        const h = home?.[key] ?? 0
        const a = away?.[key] ?? 0
        const max = Math.max(h, a, 0.001)
        const homeBetter = higherBetter == null ? false : higherBetter ? h > a : h < a
        return (
          <div key={key} className="grid grid-cols-[60px_1fr_80px_1fr_60px] gap-2 items-center py-1 text-[11px]">
            <span className={`text-right tabular-nums ${homeBetter ? "text-emerald-300" : "text-slate-300"}`}>{fmt(h)}</span>
            <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden flex justify-end">
              <div className={`h-full ${homeBetter ? "bg-emerald-500" : "bg-slate-600"}`} style={{ width: `${(h / max) * 100}%` }} />
            </div>
            <span className="text-[9px] text-slate-500 text-center uppercase tracking-wider">{label}</span>
            <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
              <div className={`h-full ${!homeBetter && higherBetter !== null ? "bg-orange-500" : "bg-slate-600"}`} style={{ width: `${(a / max) * 100}%` }} />
            </div>
            <span className={`text-left tabular-nums ${!homeBetter && higherBetter !== null ? "text-orange-300" : "text-slate-300"}`}>{fmt(a)}</span>
          </div>
        )
      })}
    </div>
  )
}
```

**Step:** mount in match page, REMOVE the old `<HeadToHead>` block from further down, run typecheck, commit.

### Task 2.3: Surface absence-driven swing in MatchVerdict

Already specified in prior plan — carry over.

### Task 2.4: Smart auto-blurb — derived insight on top of the brief

**Objective:** Above the stakes line, render a one-sentence auto-derived insight like "Bosnia score 1.7/match vs Qatar's 0.4 conceded — model leans Bosnia." Generated server-side from the same composite payload so the FE doesn't have to.

**File:** `backend/data/match_context.py` — add `_auto_blurb(ctx)` that picks the most striking statistical gap (largest gap in xG/match between sides, or biggest H2H bias, or notable absence) and verbalises it.

```python
def _auto_blurb(home, away, season_stats, absences_home, absences_away, h2h_summary):
    # Rank candidate stories by "interesting" score
    candidates = []
    h_xg = season_stats.get("home", {}).get("xg_per_match", 0)
    a_xg = season_stats.get("away", {}).get("xg_per_match", 0)
    if h_xg - a_xg > 0.5:
        candidates.append((h_xg - a_xg, f"{home} averages {h_xg:.1f} xG per match — {h_xg - a_xg:+.1f} above {away}."))
    elif a_xg - h_xg > 0.5:
        candidates.append((a_xg - h_xg, f"{away} averages {a_xg:.1f} xG per match — {a_xg - h_xg:+.1f} above {home}."))
    if absences_home:
        candidates.append((len(absences_home) * 0.6, f"{home} missing {len(absences_home)} ({', '.join(a['name'] for a in absences_home[:2])}{'…' if len(absences_home) > 2 else ''})."))
    # ... more rules ...
    if not candidates: return ""
    candidates.sort(reverse=True)
    return candidates[0][1]
```

---

## Phase 3 — In-context betting tools (~3h)

### Task 3.1: `MatchBettingPanel` — top picks + multi prefill

Carry from prior plan, no changes.

### Task 3.2 (NEW): Show api-football's prediction alongside ours on match page

**Objective:** We capture `ApiFootballPrediction.advice + winner_name + goals_home/away`. Render it as a small "Independent opinion" tile so the user sees we DON'T rely on it.

**Files:**
- Modify: `backend/api/routes/matches.py` (include api-football's prediction in the `/matches/{id}` response if present)
- New: `frontend/components/match/IndependentTake.tsx` — small tile showing "api-football: Bosnia win (advice: 'Combo Double chance: Bosnia or draw and -2.5 goals')" with a tooltip explaining we don't use it

This is a credibility tile — proves we're not blindly mirroring others. Belongs below the markets section, above the page footer.

---

## Phase 4 — Team page overhaul (NEW, ~5h)

### Task 4.1: Backend — `/teams/{code}/season-stats` + `/teams/{code}/match-log`

**Files:**
- Modify: `backend/api/routes/teams.py` — two new endpoints
- Reuse: `backend/data/team_season_aggregates.py` (from Phase 2.1)

**`/teams/{code}/season-stats`** returns the same payload as `season_aggregates()` PLUS:
- `goals_per_match` (computed from results, not xG)
- `conceded_per_match`
- `btts_pct` (% of matches with both teams scoring)
- `cs_pct` (% with clean sheet)

**`/teams/{code}/match-log?n=20`** returns last 20 fixtures with: opp_name, opp_flag_url, score, result, xg_diff, competition, kickoff. Joins `FixtureArchive` to results.

Add tests for both.

### Task 4.2: Team page — three new tiles

**Files:** `frontend/app/team/[code]/page.tsx`

Below the existing hero + "the model's outlook" panel, add:

1. **Season stats tile** — same StatCompare paired-bar pattern but solo (team vs WC field median from `/teams/radar`). Shows: xG/match, corners, yellows, possession, BTTS%, CS%.

2. **Recent results tile** — `<MatchLogTable>` with proper opponent names + scores + xG diff + a "view match" link for each row. Replaces the chip-only `<FormStrip>` on this page.

3. **Head-to-head browser** — a small "Recent meetings" panel showing top 5 H2H rows from `MatchH2H`. Each row clickable to the corresponding match if it's a WC fixture.

### Task 4.3: Team page — squad with role labels (starter vs reserve)

**Objective:** Currently the squad is just a list of names. Mark likely starters vs reserves based on `PlayerHistory.minutes` (once we have it) — for now, use `PlayerProfile.jersey_number` as a proxy (numbers 1-11 = likely starters).

**File:** `frontend/app/team/[code]/page.tsx` — group player chips by predicted role.

This is a placeholder until `/fixtures/players` is harvested (Phase 5.3).

---

## Phase 5 — Model rebuild: actually learn from harvested data (DAYS)

Each task here is half-day to full-day with mandatory backtest. Do NOT touch production until backtest confirms no degradation.

### Task 5.1: Wire FixtureArchive xG into DC re-fit input

**Goal:** Currently `backend/models/dc_ratings.py` fits Dixon-Coles on actual goals. Goals are noisy. xG is the cleanest signal we have per match.

**Approach:**
1. New parameter `use_xg: bool` in `fit_dc` defaulting to `False`.
2. When `True`, input to the fit is `(xg_home, xg_away)` from `FixtureArchive` rows instead of `(home_score, away_score)` from `Match`.
3. Skip rows where xG is missing or implausible (< 0 or > 8).
4. Add CLI tooling: `python -m backend.eval.backtest --use-xg` runs the existing 1,500 OOS comparison.

**Acceptance:** Backtest's RPS, log-loss, Brier all improve (or at least don't degrade by > 1%). Calibration ECE doesn't regress.

**Deploy:** Only after the backtest passes. Add `WC26_USE_XG_DC=1` env flag, default OFF so we can A/B locally before flipping.

### Task 5.2: Expected-corners model

**Goal:** Currently the `expected_corners` field in predictions is a hand-curated estimate per team. Replace with: `(home_corners_avg + opp_corners_against_avg) / 2` — symmetric average of attacking corner rate vs opponent's conceded corner rate. Same for cards.

**Files:**
- New: `backend/models/corners_cards_model.py`
- Modify: `backend/api/routes/predictions.py` to surface the new values

**Why this is honest:** We have corner counts per fixture in FixtureArchive. We DON'T have a validated "what causes more corners" theory — but symmetric averages are best-practice baseline for expected counts. We will mark these markets as `lower_confidence` until we backtest.

**Tests:** new `backend/tests/test_corners_cards.py` — feed synthetic FixtureArchive rows, verify the predicted expected_corners matches the symmetric average within 0.1.

### Task 5.3: Enable `/fixtures/players` in harvester

**Goal:** Get per-fixture per-player minutes/goals/rating data. Fills `PlayerHistory` from currently 0 → thousands.

**Files:**
- Modify: `backend/data/harvester_seed.py` — add to `seed_full_stack`:
  ```python
  # Per-fixture player rows from completed EPL+Bundesliga 2024 season fixtures.
  # Enqueued at priority 350 (after stats + events + predictions in priority order).
  ```
- Modify: `backend/data/harvest_processor.py` — add normaliser for `/fixtures/players` responses.

**Quota math:** ~760 fixtures × 1 endpoint = 760 jobs. At current ~150/day pace = 5 days to fill if priority is in line.

### Task 5.4: Per-player suspension impact (replaces flat -40 ELO)

**Goal:** Once we have `PlayerHistory.minutes + rating` per player, we can rank players within a squad. A suspension's impact = the suspended player's "share" of the team's minutes × rating.

**Files:**
- New: `backend/models/player_impact.py` — compute team-relative ratings from PlayerHistory.
- Modify: `backend/data/fetchers/suspensions.py` — output a per-player ELO delta instead of a flat one.

**Risk:** If the suspended player is a benchwarmer, the impact should be ~0. Current flat -40 over-penalises. Backtest required.

---

## Files touched (full list)

**Backend:**
- `backend/data/match_context.py` (new)
- `backend/data/team_season_aggregates.py` (new)
- `backend/api/routes/matches.py` (modify)
- `backend/api/routes/teams.py` (modify — 2 new endpoints)
- `backend/api/routes/predictions.py` (modify — absence swing)
- `backend/models/corners_cards_model.py` (new — Phase 5)
- `backend/models/player_impact.py` (new — Phase 5)
- `backend/models/dc_ratings.py` (modify — Phase 5)
- `backend/data/harvester_seed.py` (modify — Phase 5)
- `backend/data/harvest_processor.py` (modify — Phase 5)
- `backend/data/fetchers/suspensions.py` (modify — Phase 5)
- `backend/tests/test_match_context.py` (new)
- `backend/tests/test_team_season_aggregates.py` (new)
- `backend/tests/test_corners_cards.py` (new — Phase 5)

**Frontend:**
- `frontend/app/match/[id]/page.tsx` (Link wrapping, mount PreMatchBrief + MatchBettingPanel, REMOVE old HeadToHead from bottom)
- `frontend/app/team/[code]/page.tsx` (mount season-stats tile + match-log + H2H browser)
- `frontend/app/page.tsx` (Link scroll restoration)
- `frontend/app/api/proxy/teams/[code]/route.ts` (surface real errors)
- `frontend/components/match/PreMatchBrief.tsx` (new)
- `frontend/components/match/MatchBettingPanel.tsx` (new)
- `frontend/components/match/IndependentTake.tsx` (new)
- `frontend/components/team/FormStrip.tsx` (modify — show opponent + score)
- `frontend/components/team/MatchLogTable.tsx` (new)
- `frontend/components/team/SeasonStatsTile.tsx` (new)
- `frontend/components/team/TeamDrawer.tsx` (better error UI)
- `frontend/components/layout/ScrollRestorer.tsx` (new)
- `frontend/components/acca/MultiBuilder.tsx` (prefill mode)
- `frontend/app/acca/page.tsx` (read ?prefill=)
- `frontend/lib/types.ts` (PreMatchContext type, SeasonStats type)
- `frontend/lib/api.ts` (new api methods: preMatchContext, teamSeasonStats, teamMatchLog)

---

## Tests / validation

After each Task:
1. `pytest backend/tests/<the new test> -v` — passes
2. `cd frontend && npx tsc --noEmit` — exit 0
3. Manual: visit the changed page on live (after deploy) and verify the new section renders + has correct data for a real WC fixture (try `/match/M001`, `/team/ba` for Bosnia, `/groups`)

After each Phase:
- `bash scripts/smoke-test.sh` → 12/12 routes pass
- Sentry dashboard: no new exception events
- `/admin` overview: no degraded feeds, harvester still ticking, quota burn rate unchanged

Before each Phase 5 deploy: `python -m backend.eval.backtest --use-xg` (or `--corners`, etc) — confirm calibration metrics don't regress.

---

## Risks, tradeoffs, open questions

### Risks

- **FixtureArchive coverage is currently 10%.** Season-stat averages computed today are noisy. Mitigation: show `matches_sampled: N` next to every average so the user sees the sample size. Below n=5 → render "Insufficient data, showing tournament prior" instead of misleading number.
- **Phase 5.1 (xG-DC) might worsen short-term predictions.** xG is cleaner but lags goals at small samples. Mitigation: env flag, A/B locally, only enable after backtest passes.
- **Auto-blurb (Task 2.4) could produce hollow/circular insights** ("Brazil scored more than Iceland"). Mitigation: thresholds, rule prioritisation, hide if no rule fires above its threshold.
- **`/fixtures/players` enqueue (Task 5.3) adds 760 jobs to a queue that's already at 2,000.** Mitigation: priority 350 (after the existing 250 jobs), ETA pushes by ~5 days but doesn't conflict.

### Tradeoffs

- **HeadToHead inside vs below:** Moving it INSIDE PreMatchBrief means denser-but-scannable for desktop, more vertical scroll on mobile. Counter: collapse-by-default on mobile with a "View 3 more meetings" link.
- **Server-rendered vs client-fetched StatCompare:** Server-render is faster first paint but blocks page on the data call. The composite endpoint adds ~150ms to the match page load. Acceptable.

### Open questions for you

1. **Corners + cards markets in the UI:** Phase 5.2 builds the model but those markets aren't yet in the value board. Add them as "indicative only" (no EV claim) or hold until validated?
2. **Auto-blurb tone:** Should it lean into "the model says Bosnia" framing, or stay neutral ("Bosnia averages X vs Qatar's Y")? My instinct = neutral, let the user infer.
3. **Per-player suspension impact (5.4):** safe ceiling = -60 ELO for top player, floor = 0 for benchwarmer? Current is flat -40 regardless.
4. **Match-log endpoint depth:** last 10 vs last 20 vs last full season per team. Recommend 20 for desktop, 5 for mobile collapsed.

---

## Execution handoff

Recommended sequence:

1. **Phase 1 — TODAY** (~1.5 h, ship before bedtime). Highest payoff per minute of work.
2. **Phase 2 — TOMORROW** (~6 h). The composite endpoint is the most valuable single piece of work in the whole plan.
3. **Phase 3 — DAY 3** (~3 h).
4. **Phase 4 — DAY 3-4** (~5 h, can parallelise with Phase 3 if you have the appetite).
5. **Phase 5 — separate sprint** (3-5 days, model retrain + backtest gates).

For subagent-driven execution: dispatch one subagent per Task. Each task spec is self-contained. After EACH subagent returns, run the two-stage review (spec compliance, then code quality). Only commit + merge after both pass.

Hold Phase 5 until Phases 1-4 are deployed and stable for at least 24h — those are the user-visible wins, Phase 5 is the model-quality win.
