# Harvest → model improvements, plus EPL bootstrap plan

Written 2026-06-30 right after the GER-PAR shootout fix shipped. Two
questions on the table:

1. The harvest is drained. What does the data actually unlock for the
   model that we are not yet doing?
2. We want to start setting up for EPL — minimum to get every team,
   every player, players-mapped-to-teams, and their stats.

This doc is the plan, not a code change. Solo-ship rule applies.

---

## 1. What we actually have on disk now

VPS `data/wc2026.db` as of 2026-06-30 03:25 UTC:

| Table | Rows | What's in it |
|---|---:|---|
| harvest_jobs | 405,144 | 404,386 done / 729 skipped / 29 error |
| harvest_raw | 404,419 | 404,399 of them processed (99.99%) |
| fixture_archive | 126,300 | per-team-per-match stats with xG, shots, possession, passes, corners, cards, GK saves, goals-prevented |
| player_history | 1,986,644 | per-player-per-fixture with goals, assists, minutes, rating |
| player_profiles | 2,315 | profile data (DOB, height, position, nationality) |
| player_tournament_stats | 609 | WC26-specific aggregates |
| team_season_stats | 48 | one row per WC team, full-season-aggregate |
| match_events | 1,225 | WC26-only event timeline |
| match_lineups | 152 | 76 WC26 matches × 2 teams |
| match_statistics | 152 | same |
| team_injuries | 38 | current WC26 |
| matches | 88 | the 80 WC fixtures + bracket stubs |
| predictions | 72 | our model's locked predictions |
| prediction_snapshots | 80 | the lambda snapshots that drive live WP |
| model_calibration_log | 73 | per-match Brier outputs |

Endpoint breakdown of the raw harvest:

| Endpoint | Rows |
|---|---:|
| /fixtures/events | 79,834 |
| /fixtures/statistics | 79,832 |
| /predictions | 79,830 |
| /fixtures/players | 78,489 |
| /fixtures/lineups | 78,459 |
| /teams/statistics | 3,972 |
| /fixtures/h2h | 1,128 |
| /sidelined | 741 |
| /coachs | 741 |
| /fixtures | 508 |
| /players/topscorers | 243 |
| /players/topassists | 243 |
| /standings | 243 |

So we have ~63,000 distinct historical fixtures fully decorated (each
match has 2 fixture_archive rows, one per team), almost 2 million
player-fixture stat rows, every WC26 squad's full season aggregate, and
sidelined / injury history per team.

This is more than enough to ship the next three model upgrades that have
been on the backlog since `project_wc26_model_improvements.md`.

---

## 2. What this data unlocks for the model (ranked by ROI)

### A. Recency-weighted xG-augmented Dixon-Coles — partially shipped
Commit 2e6d293 already added Bayesian xG shrinkage + recency weighting +
composite cap on the lambdas. The shrinkage uses team_season_stats. What
isn't yet using the harvest:

- We aren't shrinking toward the **opponent-adjusted** xG average across
  the 63K historical-fixtures sample. Right now shrinkage prior is the
  team's own season average, which has selection bias when a team has
  played a weak schedule.
- Each historical fixture in `fixture_archive` has goals_prevented +
  xG. Two rows per match means we have xG-against. We can build an
  opponent-strength correction in a single sweep.

Effort: ~3-4 hours. Value: the most immediate model-quality bump
without needing new data.

### B. Goalkeeper quality lambda modifier — not yet shipped
`fixture_archive.goalkeeper_saves` and `goals_prevented` per team per
match. Aggregated per starting GK (from match_lineups), we get a
real save% and goals-prevented-above-expected per keeper. That feeds
into the away-goals lambda when the keeper is starting.

Effort: 1 day. Value: medium. Some matches the GK is the swing factor
(De Gea facing Holland 2014 etc.) — currently invisible to our model.

### C. Player-availability lambda — partially scoped
The lineup-multipliers code already exists. What's missing is a per-
player attacking-share % (goals + key-passes + xA / team total). We
have all the inputs in player_history (goals, assists, minutes,
rating). Score = recency-weighted attacking share. When a player is
out (from team_injuries / sidelined harvest), the team's effective
lambda drops by that share × replacement-factor.

Effort: 1 day for the share calc + 0.5 day to wire into the modifier
stack. Value: high. The data is sitting there unused.

### D. Score-line distribution fitting beyond Dixon-Coles
DC's tau parameter is fitted to 0-0 / 1-0 / 0-1 / 1-1 because those are
where the independence assumption breaks down. With 63K historical
fixtures we can fit tau per league + per match-context (knockout vs
group, home vs neutral), instead of one global tau.

Effort: 2 days. Value: medium. Mostly tightens probabilities at the low
score-lines, which is where the 0-0 / 1-0 / under-2.5 markets live.

### E. Calibration-by-segment audit
Use `model_calibration_log` (73 rows) joined back to match metadata to
see if we are systematically over/under-confident on:
- knockout vs group
- favourite (>60%) vs coinflip (40-60%)
- home (in CONCACAF) vs neutral

That's the diagnostic to decide WHICH segment to bias-correct first.

Effort: 0.5 day. Value: huge as a meta-step — tells us where the
remaining ROI is, instead of guessing.

### F. /predictions (api-football's own model) — comparator, not input
The 79,830 stored /predictions rows are api-football's own model. Don't
fold them into our model (would just import their biases) — but they
ARE a free third comparator alongside Opta and the market on the
calibration page. One-pass write to `competitor_predictions`.

Effort: 2-3 hours. Value: low for the model itself, useful for the
public-graded-model trust signal that monetisation depends on.

### G. Two things we should NOT do
- Fit a neural model. 63K fixtures is too few. Stay with parametric.
- Add /predictions as a model feature. Imports their biases and erodes
  the public-graded honesty pitch.

### Ranking
| Rank | Item | Effort | Estimated Brier delta |
|---|---|---|---|
| 1 | E. Calibration-by-segment audit | 0.5 day | tells us what to do next |
| 2 | A. Opponent-adjusted xG shrinkage | 3-4 hr | -0.005 to -0.010 |
| 3 | C. Per-player attacking-share lambda | 1.5 days | -0.003 to -0.008 |
| 4 | B. GK quality modifier | 1 day | -0.001 to -0.003 |
| 5 | F. api-football predictions comparator | 2-3 hr | trust signal, not model |
| 6 | D. League/context-specific tau | 2 days | -0.001 to -0.002 |

E first because it tells us if A/C/B are even worth the effort. The
audit is half a day and replaces 4-5 days of speculative work with
targeted work.

---

## 3. EPL bootstrap — the minimum to start scraping

The pivot plan in `docs/POST_WC_PIVOT.md` is the strategic backdrop:
EPL 2026-27 is free-and-public from kick-off until Jan 20 2027 so we
build calibration history. Squad + player + team data is the unblocking
work for THAT, not for picking lines today.

### What "have EPL data" actually means

For the model to predict an EPL match it needs, per team:
- Team identity (api-football team_id, display name, code, badge, primary colour)
- 2024-25 + 2025-26 season aggregates (goals for / against / xG / shots / poss / corners / fouls / cards)
- Full current squad with player_id + name + position + DOB
- Per-player season stats (goals, assists, minutes, rating, key-passes)
- Per-player recency history (last ~30 fixtures across all competitions)
- Manager / coach identity
- Current injury / sidelined list

api-football covers all of this. We've already proven the endpoints
work (the WC harvest pulled exactly these shapes).

### The 6-step bootstrap

| Step | What | Endpoint | Calls | Notes |
|---|---|---|---:|---|
| 1 | Identify EPL competition + season | /leagues?id=39 | 1 | EPL league_id is 39 in api-football |
| 2 | Get all 20 EPL teams for season 2026-27 | /teams?league=39&season=2026 | 1 | returns 20 teams with api_team_id |
| 3 | Get each team's full squad | /players/squads?team={id} | 20 | ~25-30 players per team = ~500-600 rows |
| 4 | Get per-team season stats | /teams/statistics?league=39&season=2026&team={id} | 20 | full aggregate |
| 5 | Get per-player season stats | /players?league=39&season=2026&team={id} | 20 | iterates over team, returns ~25 players each |
| 6 | Get recent fixture results so DC + ELO have a base | /fixtures?league=39&season=2025 | 1 | last 380 EPL fixtures |

Total: ~63 api-football calls. Fits inside one day's quota with room
to spare. ZERO ongoing cost beyond what we already pay for.

### The schema additions

```
ALTER TABLE teams ADD COLUMN competition_code TEXT;  -- nullable; existing 48 WC teams get 'wc2026', new EPL teams get 'epl-26-27'
ALTER TABLE teams ADD COLUMN season_id INTEGER NULL;
ALTER TABLE players ADD COLUMN competition_code TEXT;  -- NEW table; api_player_id PK
ALTER TABLE matches ADD COLUMN competition_code TEXT;  -- already in POST_WC_PIVOT plan
```

`players` table is new. Today we have `player_profiles` (DOB / height /
position) and `player_history` (per-fixture stats). We don't have a
canonical "this player is currently on this team" mapping that can
answer "who plays for Arsenal right now". That's the table this step
creates.

### Where the work lands in the repo

```
backend/data/importers/api_football/
  epl_bootstrap.py           # new — runs the 6-step flow once
  epl_recurring.py           # new — daily refresh: fixtures + lineups + injuries
backend/db/migrate.py        # add competition_code columns + players table
backend/db/seed.py           # add seed_epl_teams() callable from /admin
```

### The /admin button we'd add

Single button: "Bootstrap EPL 2026-27". One click, runs the 6 steps,
logs everything to harvest_jobs + harvest_raw with `competition_code`
already set, writes the new players + matches rows, and reports back:
"20 teams, 547 players, 380 historical fixtures imported." Idempotent —
re-running it just no-ops on already-imported rows.

### Why this works before the format-plugin refactor in POST_WC_PIVOT

We don't have to do the full multi-competition refactor to start
scraping. The data lives in tables that already exist (teams, players-
new, matches, fixture_archive, player_history). The frontend is unable
to show it without the `/c/[code]/...` route, but that's fine —
scraping early is the point so by the time we ship the route the
calibration history is already 3+ months deep.

In fact this lets us run the model against EPL **silently** for a
month before showing anything, validate Brier on graded matches, and
THEN ship the route once we know the lambdas are sane.

---

## 4. Recommended next step (solo-ship rule)

Pick ONE of:

a. **Calibration-by-segment audit** (item E from §2). Half a day, no
   data dependency, tells us if items A/B/C are even worth doing. Lowest
   risk, highest informational ROI.

b. **EPL bootstrap import** (§3). One day end-to-end. Standalone, no
   model changes. Starts the calibration clock for the paid-launch pitch
   in Jan 2027.

c. **Opponent-adjusted xG shrinkage** (item A). 3-4 hours. Direct model
   improvement before the WC final. Knockouts left = QF, SF, F = 7
   matches still to predict and grade.

The shortest path to value before the WC final ends is (c). The biggest
long-term unlock is (b). (a) is the boring-but-correct meta-move.

My recommendation: **(c) first** (model still has 7 WC matches to
predict, can ship in a single session), **then (b)** (lights up the EPL
calibration clock — the runway to monetisation), **then (a)** (informs
post-WC priorities). (a) only first if you'd rather know the audit
result before doing more model work.

Pick one and I'll ship it.
