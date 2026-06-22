# Match interruption handling — plan
*Date: 2026-06-23. Trigger: France vs Iraq suspended at HT for bad weather,
but our DB / UI showed it as `complete`. Match has only played 45 minutes.*

## 1. Why this hurts us (not just a cosmetic bug)

If we treat a suspended match as final, downstream damage compounds:

1. **Calibration log poisoned** — `calibration_logger` writes the "actual"
   outcome from the partial score. Every Brier / log-loss number from that
   day onward is wrong, and it's quiet — we don't notice until weeks later.
2. **Knockout-context model contaminated** — group standings, GD,
   head-to-head, and seeding all consume the wrong scoreline. If France
   "lose" at 0-0 on goal difference vs another contender, the bracket
   projection silently shifts.
3. **Bet settlement is wrong** — picks marked won/lost on an unfinished
   match. When the match resumes (or replays in full) we either
   double-settle or never re-settle. Either way the EV/ROI report card lies.
4. **User trust** — anyone who watched the match knows it didn't finish.
   Showing "FT 1-0" next to a delayed match is the kind of thing that makes
   a punter close the tab forever.
5. **Live polling stops** — once we mark `status = complete` the fetcher
   skips it, so even when play resumes we don't pick up the rest of the
   match.

## 2. Why it happened — the status-taxonomy gap

Current code (`backend/data/fetchers/live.py:67-68`):

    _LIVE_STATUSES = {"1H", "HT", "2H", "ET", "BT", "P", "LIVE"}
    _FT_STATUSES   = {"FT", "AET", "PEN"}

api-football actually emits at least these other states that we do NOT
model anywhere:

    SUSP  suspended (weather, crowd, VAR farce)
    INT   interrupted (short stoppage, expected to resume same day)
    PST   postponed (won't resume today)
    CANC  cancelled
    ABD   abandoned (started, will not be completed)
    AWD   awarded (3-0 walkover decision)
    WO    walkover (no kickoff)
    TBD   to be defined
    NS    not started

Two ways a match like FRA-IRQ can flip to "complete" in our DB today:

* **football-data.org path** (`backend/data/fetchers/scores.py:77`)
  queries `status=FINISHED`. If FD upgrades a suspended-then-abandoned
  match to FINISHED with the partial score, our backfill ingests it as a
  real full-time result. Their `status=FINISHED` filter is what we trust
  for "this is over".
* **api-football live poller** — match disappears from
  `/fixtures?live=all` when it goes SUSP/PST, so we stop updating the
  row, but the row is left in its last live state. Less acute, but the
  UI still reads stale "HT 1-0" forever with no indicator.

There's also no `LiveMatchState.status` value that says "delayed" — we
inherit whatever the API last sent, which in a SUSP case never made it
into our enum because we filtered it out at the gate
(`live.py:296`: `if status not in _LIVE_STATUSES and status not in _FT_STATUSES: continue`).

## 3. The model we should adopt — explicit lifecycle

Instead of the current two-bucket world (live vs done) we need three
extra terminal-ish states, mirroring how every sports book and broadcaster
models this:

    scheduled      kickoff pending
    live           1H/HT/2H/ET/BT/P (in play, ticking)
    delayed        SUSP/INT — started, paused, expected to resume
    postponed      PST — kickoff abandoned/before play
    abandoned      ABD/CANC — started, will not finish; partial result
                   may or may not stand depending on competition rules
    complete       FT/AET/PEN — real final score
    awarded        AWD/WO — decided off-pitch; we mark complete + flag

Critically: **only `complete` and `awarded` are settle-able for picks
and feed calibration.** `delayed`, `postponed`, `abandoned` push the
match into a holding bucket.

## 4. What needs to change — by surface

### 4a. Fetchers
* `backend/data/fetchers/live.py`
  - Add `_DELAYED_STATUSES = {"SUSP", "INT"}`,
    `_POSTPONED_STATUSES = {"PST"}`,
    `_ABANDONED_STATUSES = {"ABD", "CANC"}`,
    `_AWARDED_STATUSES = {"AWD", "WO"}`.
  - Stop filtering them out at line 296. Persist the status into
    `LiveMatchState.status` and update `Match.status` accordingly.
  - For SUSP/INT: keep polling (cheap — single fixture lookup), do NOT
    mark complete, freeze the elapsed minute, set
    `Match.interruption_reason` from the event log if available.
  - For ABD/PST: mark `Match.status = "abandoned"` / `"postponed"`,
    STOP polling, **do not** copy partial score into
    `home_score`/`away_score`. Stash it in
    `Match.partial_home_score`/`partial_away_score` for the recap UI.

* `backend/data/fetchers/scores.py`
  - Treat football-data `FINISHED` rows that carry a status reason of
    `AWARDED`, `ABANDONED`, or have `lastUpdated` < `utcDate + 100min`
    when minute < 90 as suspect → quarantine, don't write final score.
  - Add a second query for `status=POSTPONED` and `status=SUSPENDED`
    (FD supports both) so we positively flip our row to the right state
    instead of leaving it `upcoming`.

### 4b. Schema / persistence
Add to `Match` (in `backend/db/models.py` + migration):
  - `interruption_status` TEXT NULL  (`delayed`, `postponed`, `abandoned`,
    `awarded`, NULL)
  - `interruption_reason` TEXT NULL (free text from feed when available)
  - `partial_home_score`, `partial_away_score` INT NULL (snapshot at the
    moment play stopped)
  - `resumed_match_id` INT NULL self-FK (when a postponed match becomes a
    new fixture row)

`Match.status` stays the source of truth for "is this settle-able";
`interruption_status` carries the *why*.

### 4c. Score sanity (`backend/data/score_sanity.py`)
Add a new check: if `Match.status == "complete"` but the latest
`LiveMatchState` for the same fixture has `status in {SUSP, INT, PST,
ABD}` newer than the completion timestamp, **revert** `Match.status` to
the live status, clear `home_score`/`away_score`, and log to a new
`SCORE_SANITY_REVERTED` row so we can spot it on the admin dashboard.
This is the same self-healing pattern as the swap-fix already there.

### 4d. Calibration / settlement guards
* `backend/data/calibration_logger.py` — only enroll matches with
  `status in {"complete", "awarded"}` AND `interruption_status is null`.
  Add unit test for the SUSP/ABD case.
* `backend/data/prediction_logger.py` — same gate before computing
  realized outcome.
* `backend/betting/markets.py` + `multi_picker.py` — settlement helpers
  must refuse to grade a pick whose match is in a non-settle-able state.
  Picks placed against a since-abandoned match → mark `void`, not
  `lost`/`won` (matches every book's rules).

### 4e. UI
* `frontend` match card — when `interruption_status` is set, show:
  - delayed: amber pill "Delayed (weather) — paused at 45'" with last
    score in brackets, no "FT" badge anywhere.
  - postponed: grey pill "Postponed — rescheduling" + link to the new
    fixture once `resumed_match_id` is filled.
  - abandoned: grey pill "Abandoned at 45' (0-0)" + competition-rule
    note ("result stands" / "match to be replayed in full" per FIFA WC
    rules).
* `/admin` — add a "Match anomalies" tile counting matches in
  `delayed/postponed/abandoned` so we see them immediately, with a "force
  un-complete" action for the on-call human (us).
* Picks page — voided picks shown separately from won/lost so the report
  card stays honest.

### 4f. Knockout-context model
`backend/data/match_context.py` / `models/group_predictor.py` already
read from `Match.status == "complete"`. Once the gate above is correct,
group tables auto-recover. Add an integration test that simulates an
ABD match in matchday 2 and confirms group standings ignore it.

### 4g. Tests (lock the fix in)
* `tests/test_match_interruption.py` (new):
  - SUSP at HT → row stays live, scores not copied to FT columns.
  - PST before kickoff → status flips to postponed, partial scores null.
  - ABD at 60' → status=abandoned, partials populated, calibration skips.
  - AWD 3-0 → status=complete + awarded flag, calibration uses it.
  - Suspended-then-resumed within 4h → row goes live→delayed→live→complete
    cleanly; calibration enrolled exactly once.
  - score_sanity revert path triggers when live state contradicts a
    prior complete write.
* Extend `tests/test_quota_reserve_floor.py` style guard: SUSP polling
  must respect the same 2,500 live-reserve floor we hard-locked in
  3be8475 — a stuck-suspended fixture cannot drain the budget.

## 5. Right-now fix for France vs Iraq

Before any of section 4 ships, the existing row needs to be cleaned:

1. SSH the VPS, open the prod DB.
2. Confirm the api-football fixture's current status (SUSP / INT / PST).
3. Manually:
   - set `Match.status = 'delayed'` (or `postponed` if no resumption tonight),
   - null out `home_score`, `away_score`, `home_ht_score`, `away_ht_score`
     if they were copied from the partial,
   - set the new `interruption_*` fields (after migration ships) OR add
     a temporary marker in the existing `notes`/JSON blob,
   - delete the calibration_log row for this fixture,
   - mark any settled picks against it as `void` and refund the stake in
     the report card.
4. Force a live-poller pass so the row tracks the resumed match (or
   stays delayed until tomorrow).

If we can't ship the schema change today, do step 3 with a hand-written
SQL script + a temporary `Match.notes` string `"INTERRUPTED 2026-06-23
weather — do not settle"` so the existing settlement code skips it
(we'd add a one-line skip check in `markets.py`).

## 6. Rollout order (smallest blast radius first)

1. **Hotfix**: cleanup script for FRA-IRQ row + a one-line settlement
   skip on `notes LIKE '%INTERRUPTED%'`. Ship today.
2. **Migration + Match.interruption_status columns** (no behaviour change
   yet). Ship next.
3. **Fetcher status-taxonomy expansion** (live.py + scores.py). Ship with
   the test suite from 4g.
4. **score_sanity revert check**. Ship after #3 has been live a day.
5. **UI badges + admin tile**. Ship last — it's only useful once the
   data is correct.
6. **Settlement void rule for abandoned picks**. Ship with the UI so the
   report card reads consistently.

## 7. Decisions (researched 2026-06-23, no further sign-off needed)

User instruction was "do the research and make the best decision". Done.
Below: industry-consensus rules I'm implementing, with sources.

### 7a. WC match interruption mechanics — FIFA rule
> *"If the match has already kicked off … the match shall recommence
> at the minute at which play was interrupted rather than being replayed
> in full, and with the same scoreline."*
> — FIFA WC 2026 regulations, quoted by AP News and Sportstar
> (FRA-IRQ live coverage, 2026-06-23).

Consequence for our data model: **suspended WC matches resume on the
SAME `Match` row.** No new fixture, no row split, no `resumed_match_id`
for WC purposes. The interruption is just a pause; the row goes
live → delayed → live → complete. Calibration enrols exactly once at
the final FT.

`resumed_match_id` self-FK still goes into the schema (cheap, NULL by
default) so the data model is honest for the post-WC pivot — other
competitions (e.g. EPL, FA Cup) sometimes order full replays. For WC
it stays NULL.

### 7b. Pick void rule — industry standard, adopted as-is
Cross-checked bet365, Betfair, Sky Bet, Paddy Power. Convergent rule:

1. **Match resumes and finishes the same day (local stadium time):**
   all bets stand and settle normally on the final FT. This is the
   common case for WC (FIFA resumes within hours / next morning).
2. **Match abandoned, never finished:** all undetermined bets are
   voided (stake refunded). Determined bets stand — e.g. if at the
   moment of abandonment a market's outcome is already locked
   (over 0.5 goals after a goal was scored, BTTS=Yes after both
   teams scored, exact-score 0-0 after 89' — anything where no future
   play could change the result), those settle.
3. **Authority-awarded result (e.g. 3-0 walkover after abandonment):**
   does NOT override the void in step 2 (Serbia-Albania drone
   precedent — bookies voided even though UEFA awarded). Our model:
   `interruption_status="awarded"`, `Match.status="complete"` for
   *standings* purposes (so the group table is right), but bet
   settlement still treats it as void per market rules. This means
   one match can be "complete" for the table and "void" for picks
   simultaneously — that's the correct behaviour every book uses.

Implementation: `markets.py` / `multi_picker.py` settle helpers get a
`determined_at_abandonment(market, partial_state)` predicate. For
markets where it returns False AND `interruption_status` is set, pick
is voided. For True, pick settles on the partial state.

Sources: bet365 Abandoned Matches help page; Betfair 90-Minute Rule
(midnight local-time cutoff); Sky Bet "stand if resumes before
midnight"; Paddy Power postponed/abandoned rules.

### 7c. "Force majeure partial result stands" — handled via `awarded`
No special admin override needed. If FIFA ever declares a partial
score to stand (rare; FIFA's stated default is to resume), an admin
sets `Match.interruption_status="awarded"` + `Match.status="complete"`
via the existing /admin actions plus a one-off SQL or the score
override UI. Standings update, picks stay void per 7b.

### 7d. Resumption polling — the "midnight local time" guard
Track `Match.scheduled_kickoff_local_date`. When a match enters
`delayed`, keep polling cheaply (single-fixture endpoint, NOT
`/fixtures?live=all`) until:
  - status flips back to a live one → resume normal live polling
  - or local midnight passes without resumption → flip status to
    `abandoned` and trigger the void rule for picks
  - or a `PST` from the source → flip to `postponed` immediately

This is the same midnight cutoff every major book uses to decide
"stand vs void", so by mirroring it we don't have to invent our own
ruling timeline.

### 7e. UI copy — operator vocabulary, not bookie legalese
* delayed:    "⏸  Delayed — paused at 45' (1-0). Waiting for restart."
* postponed:  "↺  Postponed — rescheduling in progress."
* abandoned:  "✕  Abandoned at 45'. Picks voided per match-not-completed rule."
* awarded:    "⚖  Awarded 3-0 (FIFA decision). Standings updated; picks
              remain void."

---

## 8. Right-now action plan (executing today)

1. Inspect the live FRA-IRQ row state in prod (status, scores, any
   calibration_log row written).
2. Ship the **hotfix commit** before settlement runs at FT-equivalent
   time:
   - Add `Match.interruption_status` + `interruption_reason` columns
     (lightweight migration — additive, nullable, zero-risk).
   - Add SUSP/INT/PST/ABD/AWD to fetcher status handling
     (`live.py` + `scores.py`).
   - Calibration/settlement gates: refuse to enroll/settle if
     `interruption_status` is set AND match isn't `complete`+settle-able.
   - Manually flip FRA-IRQ row to `interruption_status=delayed`.
   - Tests for SUSP-at-HT, ABD, PST, resume-to-FT, midnight-cutoff.
3. Deploy via `scripts/deploy.sh`.
4. UI badges + /admin anomaly tile as a follow-up commit (not blocking).

The settlement void predicate (`determined_at_abandonment`) is the
most subtle piece — it ships as a separate, smaller commit after the
hotfix so the void logic gets its own focused review.
