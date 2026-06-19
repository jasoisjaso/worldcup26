# API Harvest & Site Completion — Implementation Plan

> **For Hermes:** Use `subagent-driven-development` skill to implement this plan task-by-task. Each task is bite-sized (2-5 min). TDD where applicable. Commit after each task.

> **Confidentiality:** This plan is internal only. Do NOT commit plan references to the public GitHub repo. All harvest details, league IDs, endpoint strategies, and schema design are proprietary.

**Goal:** Build a production-grade data harvesting pipeline that exhausts the api-football Pro quota (7,500/day) across three tiers — immediate WC data, historical major-league training data, and player-level enrichment — then wire it into the model improvement and bet builder UX.

**Architecture:** A `harvest_processor.py` layer sits between the raw `HarvestRaw` blobs and our normalised tables (`PlayerProfile`, `PlayerTournamentStats`, `TeamSeasonStats`, `PlayerHistory`, `FixtureArchive`). The existing `harvester.py` + `quota_budget.py` handle fetching + pacing. The new processor re-hydrates raw JSON blobs into queryable tables on a scheduled tick. This is the product-sale engine.

**Tech Stack:** Python 3.12, httpx, SQLAlchemy (SQLite on VPS), the existing models.py schema.

---

## Phase A: Data Layer — Solidify the Harvest Pipeline

The harvester already captures raw JSON into `HarvestRaw`. But nothing reads those blobs and normalises them. We're sitting on 48 WC squad payloads that will arrive at the next quota reset and sit in a JSON column forever.

### A.1 Build `HarvestProcessor` — post-processor that reads HarvestRaw → populates normalised tables

**Why:** `HarvestRaw.response_json` is a black hole right now. We need a scheduled job that reads successful raw blobs, extracts structured data, and writes to `PlayerProfile`, `PlayerTournamentStats`, `PlayerHistory`, `FixtureArchive`, and `TeamSeasonStats`.

**Files:**
- Create: `backend/data/harvest_processor.py`
- Modify: `backend/data/refresh.py` (register as a scheduled job)
- New tables (optional, lightweight): `PlayerHistory`, `FixtureArchive` in `backend/db/models.py`

**Priority queues (how the processor processes raw blobs):**

1. **WC squads** (`/players/squads?team=X`) → populate `PlayerProfile` (name, age, position, club, nationality, api_player_id). Dedup by `api_player_id`. ~48 blobs, ~1200 player records.

2. **Player season stats** (`/players?team=X&season=Y`) → populate `PlayerTournamentStats` + `PlayerHistory` (per-match stats per player per season). ~48 calls per season. Start with season=2023 for WC2026 relevance.

3. **Per-fixture statistics** (`/fixtures/statistics?fixture=X`) → populate `FixtureArchive` (full match stats per team per fixture: xG, possession, shots, passes, fouls). One call per fixture. The real gold for model improvement.

4. **Per-fixture events** (`/fixtures/events?fixture=X`) → populate `MatchEvent` table (goals, cards, subs). Already partially covered by the archive backfill + live poller. Processor fills gaps.

5. **Per-fixture predictions** (`/predictions?fixture=X`) → populate `ApiFootballPrediction` (api-football's own 1X2/O/U/BTTS predictions for historical fixtures). Comparison baseline.

6. **Per-fixture odds** (`/odds?fixture=X`) → the closing line on past matches. The single strongest feature for any betting model.

**New tables needed (add to `backend/db/models.py`):**

```python
class PlayerHistory(Base):
    """Per-match stats for a player in a specific fixture. One row per
    (player_id, fixture_id). Populated from /players?team=X&season=Y
    and /fixtures/players?fixture=X."""
    __tablename__ = "player_history"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_player_id = Column(Integer, nullable=False, index=True)
    api_fixture_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=True)  # our internal match id if matched
    goals = Column(Integer, default=0)
    assists = Column(Integer, default=0)
    minutes = Column(Integer, default=0)
    rating = Column(Float, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)

class FixtureArchive(Base):
    """Full match-level statistics per team. One row per (fixture_id, team_id).
    The model's Tier 2 upgrade (xG-based lambdas) absolutely needs this."""
    __tablename__ = "fixture_archive"
    id = Column(Integer, primary_key=True, autoincrement=True)
    api_fixture_id = Column(Integer, nullable=False, index=True)
    match_id = Column(String, nullable=True)  # our internal match id if matched
    team_api_id = Column(Integer, nullable=False, index=True)
    possession = Column(Float, nullable=True)
    shots_total = Column(Integer, nullable=True)
    shots_on_target = Column(Integer, nullable=True)
    xg = Column(Float, nullable=True)
    passes = Column(Integer, nullable=True)
    pass_accuracy = Column(Integer, nullable=True)
    fouls = Column(Integer, nullable=True)
    yellow_cards = Column(Integer, nullable=True)
    red_cards = Column(Integer, nullable=True)
    corners = Column(Integer, nullable=True)
    captured_at = Column(DateTime, default=datetime.utcnow)
```

The processor registers as a 10-minute scheduler job (`harvest_processor` in `backend/data/refresh.py`). Per tick: pick the 5 oldest unprocessed `HarvestRaw` entries with status_code=200, route to the correct normaliser function by endpoint, mark the HarvestRaw entry's `processed` column (new boolean field on HarvestRaw).

### Task A.1.1: Add processed flag to HarvestRaw model

**Files:**
- Modify: `backend/db/models.py` (add `processed = Column(Boolean, default=False, index=True)` to HarvestRaw)

### Task A.1.2: Add PlayerHistory and FixtureArchive tables

**Files:**
- Modify: `backend/db/models.py` (append two new class definitions)

### Task A.1.3: Build processor skeleton with endpoint routing

**Files:**
- Create: `backend/data/harvest_processor.py`
- Seven `_normalise_*` functions, one per endpoint pattern. Each reads `HarvestRaw.response_json`, extracts structured fields, writes to the target table. Processes top-5 unprocessed per tick.

### Task A.1.4: Register processor as scheduled job

**Files:**
- Modify: `backend/data/refresh.py` (add `harvest_processor` tick at 10-min interval)

### A.2 Expand `seed_wc_squads` into a full `seed_harvest_queue`

**Why:** We only seed WC squad jobs. For meaningful model improvement we need: player season stats, major league fixture sweeps, per-fixture statistics, historical odds, and predictions.

**Build:** `backend/data/harvester_seed.py` with the following seeders:

| Seeder | Priority | Calls | What it seeds |
|---|---|---|---|
| `seed_wc_squads` | 50 | 48 | `/players/squads?team=X` for all 48 WC teams |
| `seed_wc_player_stats(season=2023)` | 60 | 48 | `/players?team=X&season=2023` — the club season before WC2026 |
| `seed_wc_player_stats(season=2024)` | 61 | 48 | Same, 2024 season |
| `seed_league_fixtures(league_id=39, season=2024)` | 150 | 380 | Prem 24/25 — ~380 fixtures |
| `seed_league_fixtures(league_id=78, season=2024)` | 151 | 306 | Bundesliga 24/25 — ~306 fixtures |
| `seed_league_fixtures(league_id=140, season=2024)` | 152 | 380 | La Liga 24/25 |
| `seed_league_fixtures(league_id=135, season=2024)` | 153 | 380 | Serie A 24/25 |
| `seed_league_fixtures(league_id=61, season=2024)` | 154 | 306 | Ligue 1 24/25 |
| `seed_league_fixtures(league_id=1, season=2024)` | 100 | 48+ | WC2026 qualifiers (already covered mostly) |
| `seed_per_fixture_stats(league_id, season)` | 200 | varies | Enqueues `/fixtures/statistics`, `/fixtures/events`, `/predictions`, `/odds` for every fixture returned |

Call `seed_harvest_queue(scope="wc")` on startup (cheap — dedup prevents re-queueing). Call `seed_harvest_queue(scope="leagues")` manually from admin endpoint.

### Task A.2.1: Create harvester_seed.py with league seeding

**Files:**
- Create: `backend/data/harvester_seed.py`
- Add seeders for: WC player stats (seasons 2023, 2024), EPL fixtures, Bundesliga fixtures

### Task A.2.2: Wire seed_harvest_queue to startup + admin endpoint

**Files:**
- Modify: `backend/api/main.py` (call seed on startup)
- Modify: `backend/api/routes/harvester_admin.py` (add `POST /harvester/seed-leagues`)

### A.3 Multi-call batching for per-fixture fan-out

**Why:** The current model fetches one job per 5-min tick. After `/fixtures?league=39&season=2024` returns 380 fixtures, fanning out `/fixtures/statistics?fixture=X` × 380 × 5 leagues = a decade of harvester ticks. We need a smarter fan-out.

**Build:**
- When the processor encounters a `/fixtures` response with fixture list, it auto-enqueues the per-fixture sub-jobs (`/fixtures/statistics`, `/fixtures/events`, `/predictions`, `/odds`) at a lower priority (250) so the main sweep completes first, then the detail enrichment follows. This becomes a self-seeding pipeline: fetch fixtures → auto-queue stats/events/predictions/odds for each.

### Task A.3.1: Add self-seeding logic to harvest_processor

**Files:**
- Modify: `backend/data/harvest_processor.py` — after processing a /fixtures response, call `harvester.enqueue()` for each fixture's sub-endpoints

---

## Phase B: Model Improvement — Wire Harvested Data to the Dixon-Coles Fit

### B.1 xG-based lambdas (Tier 2 model upgrade from research)

**Why:** The current DC model fits on `(home_goals, away_goals)` pairs from the international_results CSV + our injected WC2026 results. Research shows replacing goals with xG as the fit target improves Brier by 0.02-0.04 — significant. But we need per-match xG from `FixtureArchive`.

**Files:**
- Modify: `backend/models/dc_ratings.py:118-190` (ensure_fitted)
- New: `backend/models/dc_xg_fit.py` — variant that fits on (home_xg, away_xg) instead of (home_goals, away_goals)

**Approach:**
1. `dc_xg_fit.py` mirrors the existing `dc_ratings.py` but reads `FixtureArchive` (xG column) instead of the CSV (goals column).
2. Blend ratio: 70% xG-based DC × 30% goals-based DC. The xG fit is more predictive but the goals fit anchors real results.
3. Gated behind `FixtureArchive` record count > 500. Don't switch without meaningful data.

### Task B.1.1: Build dc_xg_fit.py

**Files:**
- Create: `backend/models/dc_xg_fit.py` — mirrors dc_ratings.py structure, reads FixtureArchive.xg instead of CSV goals. Same time-decay + WC injection pattern.
- Modify: `backend/api/routes/predictions.py` — add blend logic (70/30 xG/goals when xG available).

### B.2 In-tournament adaptation rate tracking

**Why:** Track whether the model is over-fitting to recent WC results.

**Build:**
- On `/performance`, show a "last 5 matches vs pre-kickoff" delta so users can see if recent results are moving the model in the right direction.
- File: `frontend/app/performance/page.tsx` — add one more stat group below the trend callout.

### Task B.2.1: Add rolling-5 adaptation metric to /performance

**Files:**
- Modify: `backend/data/calibration_logger.py` — add `window=5` output in `rolling_calibration()`
- Modify: `frontend/app/performance/page.tsx` — render the 5-match window stats

---

## Phase C: What the Site Is Missing

### C.1 Player-level data surface

**Missing:** We have a `/team/<code>` page but it's static. No player stats, no player profiles, no ratings. FotMob and SofaScore dominate here.

**What to build (once harvest has player data):**

| Feature | Where | Harvested data needed |
|---|---|---|
| Player profile card | `/player/<id>` | PlayerProfile + PlayerHistory (appearances, goals, assists, rating) |
| Per-match top-rated player callout | Match verdict card | FixtureArchive + PlayerHistory |
| "Key player to watch" in match preview | `/match/<id>` | PlayerTournamentStats (form in WC) |
| Team squad page with stats | `/team/<code>` | PlayerProfile + PlayerTournamentStats |

### Task C.1.1: Build /player/[id] page with stats card

**Files:**
- Create: `frontend/app/player/[id]/page.tsx`
- Create: `backend/api/routes/players.py` — `GET /players/{id}` returning profile + tournament stats + history
- Modify: `backend/api/main.py` — register players route

### Task C.1.2: Add "key player to watch" to match verdict

**Files:**
- Modify: `frontend/components/match/MatchVerdict.tsx` — add brief above verdict if player data exists
- Data: already in PlayerTournamentStats table (post-processor)

### Task C.1.3: Build team squad page with sortable stat table

**Files:**
- Modify: `frontend/app/team/[code]/page.tsx` — add tab (Overview / Squad) with sortable player table

### C.2 Notifications & alerts — instant goal alerts

**Missing:** Our push system fires on value picks and big WP swings. FotMob's #1 retention driver is instant goal alerts. We have the data (LiveMatchState updates every 30s). We're not sending push on score change.

**Build:**
- In `backend/data/fetchers/live.py`, detect GOAL events and fire push immediately.
- File: modify `backend/data/fetchers/live.py` around the event-processing block (~L360-390)

### Task C.2.1: Add instant goal push notification trigger

**Files:**
- Modify: `backend/data/fetchers/live.py` — after GOAL event detected, call `send_push_notification()` with match + score + scorer name. Dedup by (match_id, score).

### C.3 "Surprise of the day" callout on homepage

**Missing:** Nothing tells users "Iraq just drew with Norway when we gave them 8%." Most shareable content format in sports prediction.

### Task C.3.1: Build surprise-of-the-day API + component

**Files:**
- Create: `backend/api/routes/extras.py` — add `GET /extras/surprise` (one SQL query)
- Create: `frontend/components/common/SurpriseCard.tsx`
- Modify: `frontend/app/page.tsx` — wire component above match list

### C.4 xG race chart on live match page

### Task C.4.1: Add cumulative xG chart below WP swing chart

**Files:**
- Create: `frontend/components/match/XGRaceChart.tsx` — simple SVG line chart with home/away cumulative xG
- Modify: `frontend/components/match/SwingChart.tsx` — render XGRaceChart below the WP chart if xG data present

### C.5 Pre-match "what to watch" auto-brief

### Task C.5.1: Build 3-bullet match brief component

**Files:**
- Create: `frontend/components/match/MatchBrief.tsx`
- Modify: `frontend/app/match/[id]/page.tsx` — wire below verdict, above swing chart

### C.6 Filterable team profile pages

### Task C.6.1: Add filters + H2H to team page

**Files:**
- Modify: `frontend/app/team/[code]/page.tsx` — add filter bar + "Compare with:" dropdown

---

## Phase D: Multi Builder Improvements

### D.1 Form-context strip per leg

### Task D.1.1: Add mini form dots to each bet builder leg

**Files:**
- Modify: `frontend/components/acca/MultiBuilder.tsx` — add FormDots strip below each leg's match label
- Data: reads `team_season_stats` form field (already populated)

### D.2 Inline injury flag per leg

### Task D.2.1: Surface injury flags on bet builder legs

**Files:**
- Modify: `frontend/components/acca/MultiBuilder.tsx` — fetch injury flags per match, show red pill if any
- Data: `GET /model/match/<id>/injury-flags` (already built, just need to call it)

---

## Phase E: Operations & Reliability

### E.1 Harvest pipeline health dashboard

### Task E.1.1: Build harvest dashboard endpoint

**Files:**
- Modify: `backend/api/routes/harvester_admin.py` — add `GET /harvester/dashboard` with queue depth, processor throughput, error rate, budget phase

### E.2 Processed-flag migration on HarvestRaw

### Task E.2.1: Add processed column + migration

**Files:**
- Modify: `backend/db/models.py` — add `processed` Boolean column to HarvestRaw
- Built as part of Task A.1.1

---

## Implementation Order

### Wave 1 — Harvest Foundation (today, 6-8 hours)
1. A.1.1 + E.2.1: HarvestRaw processed flag + PlayerHistory/FixtureArchive tables
2. A.1.3: Processor skeleton with endpoint routing + normalisers
3. A.1.4: Processor scheduled tick
4. A.2.1 + A.2.2: harvester_seed.py + admin endpoint
5. A.3.1: Self-seeding fan-out
6. E.1.1: Harvest dashboard endpoint

### Wave 2 — Data → Tables (next 2 days, 8-10 hours)
7. A.1.3 (continued): Full normaliser implementations
8. B.1.1: xG-based DC fit (gated behind FixtureArchive count)

### Wave 3 — Site Completeness (next 3 days, 12-15 hours)
9. C.2.1: Instant goal push alerts
10. C.3.1: "Surprise of the day" homepage callout
11. C.1.1-C.1.3: Player cards + squad page + key-player callout
12. C.4.1: xG race chart
13. C.5.1: Match brief
14. C.6.1: Filterable team page

### Wave 4 — Bet Builder Polish (next 2 days, 6-8 hours)
15. D.1.1: Form-context strip
16. D.2.1: Injury flags
17. D.3: Dynamic template ranking

### Wave 5 — Model Tuning (after 3+ weeks of data, 4-6 hours)
18. B.2.1: Adaptation rate tracking
19. B.1.1 (continued): Evaluate xG-based DC fit vs goals-based

---

## League ID Reference (api-football)

| League | ID | Fixtures/season | Priority |
|---|---|---|---|
| WC2026 | 1 | 104 | 50 (backfill) |
| Premier League | 39 | 380 | 150 |
| Bundesliga | 78 | 306 | 151 |
| La Liga | 140 | 380 | 152 |
| Serie A | 135 | 380 | 153 |
| Ligue 1 | 61 | 306 | 154 |
| Champions League | 2 | 125 | 160 |
| Eredivisie | 88 | 306 | 170 |
| Brasileirão | 71 | 380 | 175 |
| A-League | 188 | 156 | 180 |

Start with: WC (1), Premier League (39), Bundesliga (78). Then La Liga, Serie A, Ligue 1.

Season range: 2023 and 2024 (2025 hasn't started for most leagues).

---

## Confidentiality Checklist

- [ ] Plan doc in `docs/INTERNAL/` (gitignored)
- [ ] No fixture counts, league IDs, or endpoint strategy in any commit message
- [ ] Commit messages generic: "Add player history table" not "Seed Prem 24/25 fixtures"
- [ ] `PlayerHistory` and `FixtureArchive` table comments don't disclose the harvest pipeline
- [ ] Admin page `/admin/harvest` NOT linked from public sidebar
- [ ] Model improvement plan (Phase B) stays in `docs/INTERNAL/`

## Open Questions for Owner

1. **Scope of league seeding:** Seed EPL + Bundesliga only, or all 5 majors + Champions League in one go? Recommend: seed everything. Queue is dedup-safe so over-seeding just fills the queue; harvester plods through over weeks.

2. **Push on goals:** "GOAL — USA 1-1 Australia (65')" is pure notification, no methodology. OK to ship?

3. **Admin dashboard:** The `/admin/harvest` page reveals we have a harvest pipeline. Secure with: (a) token query param, (b) obscurity only, or (c) VPS-internal only? Recommend (a) — simple, shareable.
