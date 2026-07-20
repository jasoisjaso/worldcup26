# EPL Pivot — Execution Plan (post-WC)

Written 2026-07-20, the day after the World Cup final (Spain 1-0 Argentina).
This is the DO doc. The strategy is in `POST_WC_PIVOT.md` (2026-06-22); this
converts it into dated, code-level work now that the tournament is actually
over and we know the real dates.

## The hard deadline that drives everything

**EPL 2026-27 kicks off Friday 21 August 2026** (a week later than normal
because of the World Cup). Fixtures were released 19 June 2026 — they exist
now, we can import them today. Season ends 30 May 2027. Opening game:
Arsenal v Coventry (promoted) at the Emirates, Fri 21 Aug.

That gives us **~4.5 weeks** (Jul 20 → Aug 21) to go from a finished
single-tournament WC app to a live EPL predictor taking its first graded
predictions on MW1. Miss Aug 21 and we lose a month of graded-prediction
sample before the Boxing Day acquisition window — the whole free-until-Jan
strategy leans on having a fat calibration sample by then.

## Where the code actually is today (verified 2026-07-20)

Reusable as-is (competition-agnostic — confirmed by reading the files):
- `backend/models/` — poisson, dc_ratings, elo_model, form, calibration,
  platt_calibration, venue_advantage, prediction_inputs. Take lambdas in,
  give probabilities out. Don't care about competition.
- `backend/betting/` — markets, sgm, ev, kelly, accumulator. Pure score-grid
  math, competition-blind.
- `backend/data/harvester.py` — hits api-football. EPL is league **id 39**
  there; the same fixtures/results/lineups endpoints work. Quota budget +
  feed health already built.
- Prediction logging + calibration + Brier scoring — works off any Match rows.
- Frontend match cards, value board, acca builder, SGM pricer, Report Card,
  Track Record — all competition-ignorant.

NOT done yet (this is the real work — the June plan's "Week 1" never started):
- **Match table has NO `competition_code` column.** `group` + `matchday` are
  WC-only. No `competitions` / `seasons` tables. Schema is single-tournament.
- `backend/models/group_predictor.py`, `knockout.py`, `tournament_sim.py`,
  `wc2026_bracket.json` are WC-format-specific. EPL needs a league-table +
  remaining-fixture simulator instead.
- Only WC importers exist (`importers/wc2026_*.py`). No EPL importer.
- Routes `/groups`, `/match3`, `/bracket`, `/winner`, `/scenarios` are WC-only
  concepts. Nav was just cleaned up for the post-tournament state (Awards
  leads) but is still fundamentally a WC nav.
- Seed loads WC fixtures from openfootball worldcup.json only.

## Scope decision: DON'T build the full multi-comp abstraction yet

The June doc's format-plugin registry + `/c/[code]/` routing is the *right*
long-term shape, but building the whole generic abstraction before we've run
a single EPL season is over-engineering on a deadline. **Ship EPL as the
second competition the pragmatic way, refactor to generic once it's proven.**

Concretely: add `competition_code` (default it, backfill wc2026), get EPL
running alongside, and only pull the format-plugin abstraction out once BOTH
WC (frozen, archived) and EPL (live) are working. Two concrete implementations
beat one speculative abstraction.

---

## Phase 0 — Freeze & archive WC2026 (this week, Jul 20-22)

The WC is done and the site is now a wrap-up. Lock it so it can't rot or
burn api-football quota, and so it stands as the permanent public track
record (the calibration IS the moat — the graded WC ledger is an asset).

- [x] Homepage redirects to /awards now the final is complete (fixed the
      `redirect()`-swallowed-by-try/catch bug — that's why the live site was
      stuck showing MD3). Deployed b9dee23.
- [x] Awards page + nav are complete-aware (no "updated every 60s").
- [ ] Turn OFF the WC harvester cron on the VPS so it stops polling
      api-football for a finished tournament (quota = money once EPL needs it).
      Check `scripts/cron-*.sh` + crontab; disable the WC team-news + match-brief
      + refresh jobs. Keep a DB backup.
- [ ] Snapshot the final WC DB to `vps-backup/_shared/wc26-FINAL.<ts>.db` —
      this is the permanent graded record. Never overwrite it.
- [ ] Add a one-line banner to the WC pages: "2026 World Cup — final results.
      EPL 2026-27 predictions land here from Aug 21." Bridges the dead-air month.

## Phase 1 — Schema: make the DB competition-aware (Jul 22-26)

Non-destructive migration. WC2026 keeps working identically throughout.

- [ ] `backend/db/migrate.py`: add `competitions` + `seasons` tables per the
      June doc schema. Add columns to `matches`:
      `competition_code TEXT`, `season_id INTEGER NULL`, `round_label TEXT NULL`.
      Keep `group`/`matchday` but make them nullable (only filled for
      tournament formats).
- [ ] Backfill: `UPDATE matches SET competition_code='wc2026'` on every existing
      row. Insert the `wc2026` competition row (format='tournament-groups-knockout',
      active=false — it's finished).
- [ ] Every query in `backend/api/routes/*` that lists matches gets a
      `competition_code` filter (default to the active comp). This is the
      surgical bit — grep for `.query(Match)` and scope each one.
- [ ] Tests stay green (`backend/tests/`). Add a migration test that asserts
      104 WC matches all got `competition_code='wc2026'`.

## Phase 2 — EPL importer + backfill (Jul 26 - Aug 2)

The model needs history before it can predict MW1 sensibly. DC + ELO ratings
are worthless cold.

- [ ] `backend/data/importers/epl_2026_27.py`: import the released 2026-27
      fixture list. Source options in priority order:
      1. openfootball eng-england repo (CC0, no quota) for fixtures.
      2. football-data.org (free tier) as cross-check.
      3. api-football league=39 season=2026 for lineups/results during the season.
- [ ] Seed the 20 EPL teams (name, crest, colours) into `Team` — note Team
      currently keyed by FIFA code; EPL clubs need a code scheme (use
      api-football team ids or short slugs like `ars`, `che`). This may need a
      `Team.competition_scope` or just distinct code prefixes.
- [ ] **Backfill 2024-25 + 2025-26 EPL results** so Dixon-Coles + ELO have a
      base. Without ~2 seasons of history the opening-week λ estimates are noise.
      openfootball has completed seasons; import them as `status='complete'`
      historical Match rows under a past season_id (they feed ratings but aren't
      shown as upcoming).
- [ ] Fit DC + ELO on the backfilled history. Sanity-check: model should rank
      Liverpool/Arsenal/City top, promoted sides (Coventry + others) bottom.
      If it doesn't, the import is wrong.

## Phase 3 — League-format simulator (Aug 2-9)

EPL has no groups/bracket. It needs a season-projection sim.

- [ ] `backend/models/season_sim.py`: given current table + remaining fixtures,
      Monte-Carlo the rest of the season → P(title), P(top-4/UCL), P(top-6),
      P(relegation) per team. This is the EPL analogue of `tournament_sim.py`.
      Reuse the same per-match λ → score-grid the WC sim already uses.
- [ ] New route `/table` (league standings + projected finish) replacing the
      WC `/groups`+`/bracket`+`/winner`. A "who wins the league / who goes down"
      page is the EPL headline equivalent of "who lifts the trophy".
- [ ] Value board + acca + SGM + model-picks work unchanged once they read EPL
      matches — verify, don't rebuild.

## Phase 4 — Frontend EPL surface (Aug 9-16)

- [ ] Homepage: default to the active competition's upcoming matches. Once
      Phase 1 lands a `competition_code` filter, the existing MatchesPage renders
      EPL fixtures with zero card-component changes.
- [ ] Nav: EPL version — Fixtures, Table (w/ projections), Value Board, Model
      Picks, Report Card, Track Record, How It Works. Drop group/bracket/scenario
      concepts entirely for EPL.
- [ ] Rewrite /how-it-works to be competition-neutral ("this model predicts
      football matches and grades itself in public") not WC-specific.
- [ ] **Email capture field** on the value board + post-match view (the June
      plan's single most important growth lever — it's the only bridge from
      free-traffic-now to paid-conversion-Jan). One field, ConvertKit/Resend/
      Buttondown or a simple `subscribers` table + Resend. Copy: "weekly model
      report card + Boxing Day specials + early-adopter $9/mo lock-in".
- [ ] Site banner from MW1: "Free until ~20 Jan 2027 — early adopters lock
      $9/mo for life."

## Phase 5 — Live-ops for a weekly league (Aug 16-21)

WC was a 4-week sprint; EPL is a 9-month marathon with a weekly rhythm.

- [ ] Cron: nightly EPL refresh (fixtures/results), matchday lineup pull ~1h
      before each kickoff, post-match settlement + prediction grading. Reuse the
      WC harvester + quota budget; add per-comp priority so EPL isn't starved.
- [ ] Prediction lock timing: predictions must lock BEFORE kickoff and be
      immutable (the ledger is the moat — never let a pick be edited after the
      fact). Verify the lock logic works on a weekly cadence, not just the WC
      daily burst.
- [ ] Confirm calibration/Report Card reads EPL predictions and grades them
      separately from the frozen WC sample (per-comp calibration — a noisy early
      EPL model shouldn't drag the honest WC grade, and vice versa).

## MW1 launch (Fri 21 Aug 2026)

First locked, publicly-graded EPL predictions go live for the opening card.
From here it's: run free + ad-free, capture emails, compound the calibration
sample, and hit Boxing Day (26 Dec — densest bet week of the AU calendar)
with a fat track record and a warm email list.

---

## How we actually earn a dollar (the money path, unchanged from June, now dated)

The revenue model that survives Australian law (IGA 2001 / ACMA — offshore
affiliate funnels get the site ISP-blocked; running a book needs a six-figure
licence): **subscription first, Aus-licensed affiliate second.** Detail +
legal citations in `POST_WC_PIVOT.md` §4. The dated path:

| When | Move | Why |
|---|---|---|
| Now (Jul-Aug) | Register Pty Ltd + ABN (~$500). Draft ToS, privacy policy (Privacy Act 1988), responsible-gambling page (18+, BetStop, 1800 858 858). Pro-indemnity insurance ($800-1500/yr, required to charge for tips). | Legal foundation before a cent changes hands. |
| Aug 21 → Jan 20 | EPL fully **free + ad-free**. Every pick locked + publicly graded. Banner: "free until Jan 20, early adopters get $9/mo for life". | Calibration sample fattens; trust + SEO compound; ~150 graded EPL picks by Jan beats launching paid on ~80. |
| Aug onwards | **Email capture** on value board + post-match. This list is the ONLY bridge to paid. Without it, Jan 20 is a launch into the void. | The single highest-leverage thing to build in Phase 4. |
| Dec 2026 | Boxing Day specials: pre-built model accumulator across the full Boxing Day card (shareable card) + year-in-review email ("model went X% season-to-date") + $9/mo lock-in for pre-Jan signups. | Boxing Day + NYE = densest AU bet week, peak attention, everyone on holiday. Max list growth. |
| Nov-Dec 2026 | Build + test Stripe Checkout + paywall middleware + magic-link auth (Apple/Google Pay via Stripe). | Infra ready before launch, not during. |
| **~20 Jan 2027** | **Paid launch.** Single tier $15/mo or $99/yr; early-adopter list locks $9/mo. Free tier persists with limits (3 picks/day, no alerts) so SEO/trust keep compounding. | Back-to-work week; Jan 1 is dead (cricket/beach). Jan 20 is when EPL attention resumes. |
| Feb 2027 | First affiliate: **Sportsbet** (largest AU operator, easiest onboarding). Referral code per value pick with a Sportsbet line, clearly disclosed. Only ACMA-register-licensed operators, ever. | Layer-on revenue on top of subs, not a foundation. |
| Mar-Apr 2027 | Add Pointsbet + TAB affiliates + admin reconciliation view (their dashboards drift from our logs). | Diversify affiliate revenue. |
| When rev >$75k AUD/yr | Register for GST (Stripe flips a flag). | Legal threshold; free + fast. |

Rev estimate (June research): subscription at 5-10% paid conversion at
$15-30/mo on 1k DAU = $5k-30k/mo. Affiliate CPA $50-200/qualifying signup but
volatile without SEO scale. Subs are the foundation, affiliate the layer-on.

### The three things that kill it
1. **Lying about track record.** The public graded ledger is the moat. Keep
   the locked-prediction + Brier scoring honest even if no subscriber checks.
2. **Going wider than Australia before AU pays the rent.** Each jurisdiction
   is weeks of gambling/affiliate compliance for marginal upside.
3. **Building a book / offering credit / offshore-affiliate funnel.** Not at
   any scale we'll reach; the offshore funnel gets the whole site blocked.

## Open decisions (surface, don't decide today)
- **Domain.** `wc26.tinjak.com` is tournament-specific. The multi-comp/paid
  future wants a proper `<name>.com.au` (affiliates weight `.com.au`; signals
  AU jurisdiction). Pick before EPL SEO compounds onto the WC subdomain —
  ideally BEFORE Aug 21 so MW1 predictions land on the permanent domain.
- **Team code scheme** for EPL clubs (api-football ids vs slugs) — decide in
  Phase 2, it ripples through URLs.
- **Email provider** (Resend + own `subscribers` table vs ConvertKit) — decide
  in Phase 4.

## Immediate next actions (in order)
1. Kill the WC harvester cron on the VPS + snapshot the final DB (Phase 0).
2. Buy the domain (blocks nothing else but has the longest lead time for SEO).
3. Schema migration: `competition_code` + `competitions`/`seasons` (Phase 1).
4. EPL importer + 2-season backfill + refit DC/ELO (Phase 2).
