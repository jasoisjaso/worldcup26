# API-Football Utilisation Audit — 2026-07-02

Context: owner wants EPL + other-league modelling after WC2026. This audit
checks whether the api-football Ultra plan (75,000 calls/day) is being fully
exploited, what data is captured vs wasted, and what the EPL build needs.

## Headline numbers (observed 2026-07-01, 23:12 UTC)

| Metric | Value | Verdict |
|---|---|---|
| Daily quota | 75,000 | — |
| Used on audit day | ~4,800 (70,218 remaining at 23.2h) | **~94% of quota UNUSED** |
| HarvestRaw blobs archived | 404,419 | healthy |
| Unprocessed backlog | 20 (was 331K on Jun 28; drain worked) | healthy |
| Leagues seeded | 21 (EPL, Championship, Bundesliga, La Liga, Serie A, Ligue 1, UCL + 14 more) | good base |
| Seasons | 2010+ for 9 major leagues, 2016+ others | good base |

The seeded historical harvest has essentially COMPLETED — that is why quota
goes unused. The queue needs new work items, not more capacity.

## Endpoint coverage

Captured and normalised into tables:
`/fixtures`, `/fixtures/statistics` (xG), `/fixtures/events`,
`/fixtures/players`, `/fixtures/lineups`, `/fixtures/h2h`, `/predictions`,
`/standings`, `/players`, `/players/squads`, `/players/topscorers`,
`/players/topassists`, `/coachs`, `/sidelined`, `/teams/statistics`.

Gaps found (and status):

1. **`/odds` was never harvested — zero blobs.** The normaliser stub existed
   but nothing enqueued jobs. CRITICAL nuance: api-football serves pre-match
   odds only from ~7 days before kickoff and EXPIRES them ~14 days after.
   There is NO historical odds backfill — an odds archive can only be built
   by capturing forward. **FIXED 2026-07-02**: `seed_upcoming_odds()` in
   `harvester_seed.py` + `odds_harvest_seed` scheduler job (6h tick) enqueues
   `/odds?league&season&date` per watched league per day, 7-day lookahead,
   deduped per date. `ODDS_WATCH` currently `[World Cup (league 1)]`;
   **add `{"league": 39, "season": 2026}` when the EPL season starts.**
2. **`/odds` pagination caveat**: ~10 fixtures/page, generic fetcher takes
   page 1 only. Fine for WC knockout days (<=2 fixtures), NOT fine for EPL
   matchweeks (10 fixtures, borderline). Before EPL: fan out per-fixture
   `/odds?fixture=<id>` jobs instead of per-date.
3. **`_normalise_odds` is still a no-op** (blobs stored raw). Before EPL
   modelling, normalise into an OddsArchive table (fixture, book, market,
   price, captured_at) so CLV and de-vig training data are queryable.
4. `/odds/live`, `/transfers`, `/trophies`, `/venues` unused — low value for
   now, no action.
5. `/injuries` — in use via `injuries_persist` (48 calls/6h). OK.

## Sharp-odds (Pinnacle) anchor — was dead, now fixed via a different route

- `sharp_odds.py` (SportsGameOdds trial) has NEVER succeeded:
  `leagueID=FWC` -> 400. Probe of their `/v2/leagues` shows the trial tier's
  soccer coverage is **UEFA Champions League + MLS only. No World Cup, no
  EPL.** The feed was structurally dead, silently, since it shipped —
  `anchored_to_sharp` pick grading has been running without its anchor.
- **FIXED 2026-07-02**: `pinnacle` added to The Odds API bookmaker list in
  `odds.py`. Free (billing is ceil(books/10) x markets; 4 books still 1 unit
  per market). Verified live in the server cache: M081 USA-BIH home 1.34 /
  draw 5.00 / away 9.25 with pinnacle listed per market. Pinnacle now flows
  into `_book_odds` + the `OddsCache` archive on every fetch.
- Follow-up: point the sharp-anchor/blend path at the Pinnacle entries in
  `_book_odds` instead of the dead SGO cache; the SGO scheduler job still
  400s every 6h (harmless, noisy) — remove it or repoint at UCL next season.

## Odds staleness / CLV fix (The Odds API side)

- 8h cache TTL rationed the 500-credit/month key but froze "closing lines"
  up to 8h before kickoff -> the CLV metric (-3.4%) was measuring against
  stale lines, and homepage EV numbers froze through match windows.
- **FIXED 2026-07-02**: `refresh_near_kickoff()` + `odds_prekickoff` job
  (10-min tick): forces one fetch when a match starts within 90 min and the
  cache is >45 min old. ~4-8 credits/day; the July budget covers it (key
  reset to 498 on Jul 1; ~495 after validation probes).
- CLV numbers logged BEFORE 2026-07-02 should be treated as unreliable.
  Expect the metric to become meaningful over the remaining ~30 WC picks.

## Betting-process lesson from M081 (USA-BIH)

Model said Draw @ 4.80 was "+15% EV", but Pinnacle sold the same draw at
5.00-5.25 (sharp fair ~18.6% vs our 23.2%). A soft-book price SHORTER than
Pinnacle's is a negative-CLV bet by construction, whatever the model says.
Rule going forward: check every recommended pick against the Pinnacle line
(now in `_book_odds`) before surfacing it as value.

## EPL readiness checklist (when season starts, ~Aug 2026)

1. `ODDS_WATCH` += league 39 (and 40/78/140/135/61/2 as desired) — 1 line.
2. Fan out `/odds` per-fixture to beat pagination (item 2 above).
3. Implement `_normalise_odds` -> OddsArchive table.
4. Seed 2026-27 season fixtures once published (`seed_league_fixtures([39])`).
5. Repoint the sharp anchor at Pinnacle via The Odds API (`soccer_epl` sport
   key) — budget check: 500 credits/month is tight for a 38-matchweek
   season; consider the paid tier or lean on api-football `/odds` (Pinnacle
   is among its books) once normalisation lands.
6. The Dixon-Coles + ELO core is league-agnostic; the WC-specific parts are
   the tournament simulator and bracket logic. The model layers (xG
   modifiers, key-absence, rest/travel) all read from FixtureArchive-family
   tables that the 21-league harvest already populates back to 2010.
