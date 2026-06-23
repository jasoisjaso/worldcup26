# Live page: knockouts, simultaneous matches, and shootout UI

Research brief written 2026-06-23 before touching code, after the Argentina vs
Austria match exposed the missed-penalty bug. Three concerns, each researched
against (a) api-football's actual behaviour, (b) our current code paths, and
(c) what good production apps do.

## TL;DR — what's actually a risk and what isn't

| Concern | Current state | Real risk? |
|---|---|---|
| Tomorrow's MD3 simultaneous group games | Wired correctly — confirmed by `test_concurrent_live_matches.py` | LOW. Two minor cleanups. |
| Knockout match marked "complete" prematurely | YES, FT trap exists (verified) | HIGH. Will mis-render every knockout that goes to ET. |
| Penalty shootout score not captured | YES, we never read `score.penalty.home/away` | HIGH. Will report the wrong final score for every shootout. |
| Shootout UI presentation | Nothing custom — would render as "Penalties FT" badge with goals as the score | HIGH. Reads as a regular FT match, not a shootout. |

The knockout-FT trap is the most urgent because the WC2026 R32 starts in 5
days (June 28). Group MD3 tomorrow is the smaller worry.

---

## Concern 1 — Knockout-FT trap (HIGH priority)

### What api-football actually does

Confirmed from api-football docs + Sportmonks parallel docs:

```
Knockout match going to ET + pens:
   NS → 1H → HT → 2H → FT (briefly!) → BT → ET → HT-ET → ET → AET → P → PEN
```

Quote from Sportmonks docs (api-football behaves the same):
> "When a game goes into extra time, the FT status will be presented for a
> few seconds and then move to the BREAK status."

### What our code does (the bug)

`backend/data/fetchers/live.py:442`:

```python
if status in _FT_STATUSES and match.status != "complete":
    match.status = "complete"
    match.home_score = home_score
    match.away_score = away_score
```

Where `_FT_STATUSES = {"FT", "AET", "PEN"}`. So during that few-second `FT`
window before `BT/ET`, we mark a knockout match complete with its 90'
score. The match THEN flips to ET; our row is technically still polled
(ET is in `_LIVE_STATUSES`), but `match.status` stays `complete` so:

- The /live page drops the match from its "in play" feed
- The "Recent / Just finished" strip surfaces it
- The UI shows the 90' score for the entire ET period (15-30 min)
- Score is later corrected when AET/PEN arrives, but the damage is done

### Fix (proposal — not coded yet)

Two clauses, both required:

1. **Don't complete on `FT` for knockout matches.** A match is "knockout"
   when `matchday >= 4` (group stage is matchday 1-3, R32 onward is 4+).
   Belt and braces: also when api-football's response includes
   `score.extratime` or `score.penalty` populated (which only appear on
   matches that went to ET / pens).

2. **Only complete on `AET` or `PEN` for knockouts.** `FT` for a knockout
   means "90' done, see you in extra time" — not "match decided".

Concrete change to `refresh_live_fixtures`:

```python
is_knockout = (match.matchday or 0) >= 4
# For knockouts, "FT" means 90' finished — match could be going to ET/pens.
# Wait for the unambiguous AET or PEN signal before locking in the result.
match_decided = (
    (status == "FT" and not is_knockout)
    or status in ("AET", "PEN")
)
if match_decided and match.status != "complete":
    ...
```

Plus a stale-row sweep tweak: bump the 5-min cutoff to 10 min for matches
in `BT` status (extra-time break can last 5-7 min, +5min poll gap = 10).

### Test we should add

`test_knockout_ft_trap.py` — feed the poller a single-fixture response
with status="FT" + matchday=4 + non-zero `score.extratime`, then a follow-up
with status="ET" → match.status must stay "in_play" not "complete" through
the first tick.

---

## Concern 2 — Simultaneous matches (LOW priority, already correct)

### What we already do right

- `/fixtures?live=all` returns ALL live fixtures in one HTTP call
- Per-fixture sub-fetches (events, stats) run inside the loop, one set per
  match, no shared state
- Per-fixture memos (`_FIXTURE_MEMO`, `_STATS_TICK_COUNTER`,
  `_LAST_STATS_RAW`) are dicts keyed by fixture_id, so two fixtures can
  never share a counter
- Push dedup_keys include `match.id` so a goal in one match can't suppress
  the notification for the other
- LiveHub React component renders `data.matches.map(...)` with per-card
  `useState`, so the goal-flash detector in `LiveMatchCard` is per-match

`test_concurrent_live_matches.py` (added today) locks this in end-to-end:
two simultaneous fixtures produce independent state rows + independent
history ticks + 2 distinct dedup_keys on simultaneous goals.

### Cost check for tomorrow

MD3 = 6 groups × 2 matches = 12 fixtures, but in 6 pairs (not 12 at once).
Worst case: 2 simultaneous matches × 90 min each:

- `/fixtures?live=all`: 1 call/30s = ~180 calls/match window
- `/fixtures/events` × 2: 2 × ~180 = ~360 calls
- `/fixtures/statistics` × 2 (every other tick): 2 × ~90 = ~180 calls

Per simultaneous-pair: ~720 calls. Three pairs across MD3 day: ~2,160
calls. Well inside the 7,500/day Pro budget AND inside the
2,500-call live-reserve floor (commit `3be8475`). No quota risk.

### Two small UI nudges worth doing

1. The LiveHub sort is `-elapsed_min` (most-elapsed at top). When 2 games
   are at the SAME minute it'll sort by insertion order, which is jittery.
   Tie-break by kickoff time for stability.

2. The browser Notification `tag` field is set to `m.match_id`. iOS Safari
   replaces same-tag notifications instead of stacking — so a Brazil goal
   would replace an Argentina goal alert. We want both to show. Drop the
   tag OR include a timestamp suffix.

---

## Concern 3 — Penalty shootout: data + UI

### Data we're missing (HIGH priority)

`/fixtures?live=all` returns a `score` object we currently ignore:

```json
{
  "fixture": { "id": ..., "status": { "short": "PEN", "elapsed": 120 } },
  "goals":   { "home": 1, "away": 1 },              ← we read this
  "score": {
    "halftime":  { "home": 0, "away": 0 },
    "fulltime":  { "home": 1, "away": 1 },
    "extratime": { "home": 1, "away": 1 },
    "penalty":   { "home": 4, "away": 3 }            ← we DON'T read this
  }
}
```

`goals` is the aggregate score INCLUDING extra time but NOT including the
shootout. The shootout score lives in `score.penalty` and is only present
once shootout has begun.

Without this, a knockout ending 1-1 after ET that Argentina wins on pens
shows on our UI as "Argentina 1-1 France (FT)" forever — same score as
a draw. We need to add columns to `LiveMatchState` + `Match`:

- `shootout_home_score` (nullable int)
- `shootout_away_score` (nullable int)
- `shootout_winner` (nullable str — "home" / "away" / None)

The aggregator already separates regulation pens from shootout pens
(`shootout_penalty_goals/misses` in `PlayerTournamentStats`, added this
morning). So per-kicker stats are right; we just need the team-level
shootout score too.

### UI presentation (researched from production apps)

What the best apps converged on for live shootout display:

**Sofascore / FotMob / ESPN — common pattern:**

```
       1 - 1   (4 - 3 pens)         ← big aggregate score at top
   Argentina        France
   ● ● ● ● ○                       ← scored ● / missed ○ / pending ◌
   ● ● ○ ●                          ← row per team, left-to-right
                ↑
        current kicker highlighted
```

Plus a per-kick log below:

```
  ARG  Messi      ✓ scored
  FRA  Mbappé     ✓ scored
  ARG  De Paul    ✓ scored
  FRA  Griezmann  ✗ missed (saved)
  ARG  Álvarez    ✓ scored
  FRA  Tchouaméni ✓ scored
  ARG  Otamendi   ✓ scored
  ...
```

**Apple Sports** does the same thing but minimal: just the row of dots
under each team name, no per-kick log.

**Wikipedia / Law 10 confirms:**

- 5 kicks each, then sudden death
- FIFA officially classes the match as a draw — shootout goals do NOT
  count toward player goal totals
- This validates today's decision to bucket shootout pens separately
  in `PlayerTournamentStats`

### Our shootout-UI proposal (mock — not coded yet)

Build a new `<ShootoutTracker>` React component that renders below the
score-row inside `LiveMatchCard` when `state.status in ("P", "PEN")`:

```
ARGENTINA      ●  ●  ●  ●  ●         5
FRANCE         ●  ●  ✕  ●  ●         4  ← faded once decided
```

- Filled circle = scored (team's primary colour)
- ✕ in a circle = missed (rose-400)
- ◌ pulsing = current kicker
- Score on the right
- Big "PENALTIES" badge above, swapping the LIVE pulse for a calmer
  amber pulse so it reads as "in shootout" not "regular live"
- Aggregate score under team names reads `1-1 (4-3 pens)`

A "Per-kick log" expand below shows each kicker + name + outcome (we
already collect this — `MatchEvent` with `type="Goal"` and either
`detail="Penalty"`/`detail="Missed Penalty"` and `elapsed > 120` or
`comments contains "Shootout"`).

### What we should NOT build

- A "predict the next kicker" interactive — too gimmicky, no data edge
- A goalkeeper save heatmap — needs Opta-tier data we don't pay for
- A "shootout simulator" — irrelevant to the betting use case

---

## Recommended order of work (for next session)

All gated on the user's go-ahead. Nothing coded yet from this brief.

1. **Knockout-FT trap fix + test** (1 patch, ~30 lines) — most urgent
2. **Read + persist shootout score** from `score.penalty.*` (1 patch +
   2 migration columns + 1 test)
3. **`<ShootoutTracker>` component + wire-in** (1 component, ~80 lines)
4. **Per-kick log expand** (small UI add)
5. **Notification tag fix** (1-line change so iOS doesn't collapse goals)

Steps 1+2 should ship together — they're both data-correctness fixes.
Step 3+4 are presentation, ship in a second cut once data is right.
