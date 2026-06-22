# Plan: Calibration Guardrails + Picks UI Overhaul (2026-06-22)

Research-first plan for the four problems you raised. Nothing built yet — this
is the proposal. Sources: OddsIndex/Outlier/OddsShopper +EV guides, the model
calibration literature from the earlier audit, and a full read of the current
code (multi_picker, betting routes, dc_ratings, nav, the three picks pages).

==============================================================================
PROBLEM 1 — The model makes "wild" bets (+68% EV Australia v USA, lost)
==============================================================================
ROOT CAUSE (confirmed in code, not guessed):
  - backend/betting/multi_picker.py has a LOWER edge floor (MIN_EDGE_OVER_BOOK
    = 0.05) but NO UPPER cap. A +68% EV leg sails straight through.
  - The single-pick value board (betting.py) DOES compute reliability tiers
    (solid / speculative / longshot via market.reliability_tier) and sorts by
    them — but the MULTI picker ignores tiers entirely.
  - The Australia-v-USA case is the textbook failure the research names:
    "overestimating your edge is the fastest way to lose money." A model prob
    far above the (sharp) market implied is almost always model error, not a
    real edge — the market is sharp; a 68% EV gap means OUR number is wrong.

WHY IT'S NOT A DATA PROBLEM (important — you said "grab all the history"):
  We ALREADY train on the right data. dc_ratings.py fits attack/defense from
  8 years of international results (martj42), time-decayed (~1yr half-life),
  competitive matches weighted 2x, World Cup matches 2.5-5x, plus our own WC
  results injected at 5x, PLUS the harvested FixtureArchive xG feeds the live
  modifiers. The foundation is sound. The leak is the ABSENCE OF A GUARDRAIL
  on the output, not missing inputs. So the fix is calibration discipline +
  a sanity gate, not a data-harvest expansion (that would "over-extend" exactly
  as you warned).

THE FIX (small, surgical, testable):
  A) Upper-EV sanity gate (the headline fix). In multi_picker AND the value
     board, reject / down-rank any leg whose model prob exceeds the SHARP
     market implied by more than a tier threshold. Reuse the existing
     reliability_tier(): only "solid" (<=30% over the book) legs may seed a
     model-picked multi; "speculative" allowed only as a single flagged pick,
     never auto-staked; "longshot" never published. This directly kills the
     +68% EV multi leg.
  B) Cap absolute EV. Add MAX_EDGE_OVER_BOOK (e.g. 0.25 = 25%). A combined or
     per-leg EV above that is treated as a red flag (model error / stale line),
     not a green light. Surface it in the UI as "implausible edge — skipped"
     so the discipline is visible, not silent.
  C) Anchor edge to the SHARP line when we have it. The picker currently
     devigs the soft book (Odds API). When a Pinnacle sharp anchor exists for
     the fixture, measure edge against THAT — soft-book vig/errors are exactly
     what inflates phantom EV. (We already pull sharp odds; just thread them in.)
  D) Min-sample confidence. A leg on a team with thin DC fit / few archived
     fixtures gets its edge SHRUNK (Bayesian, toward the market) before the
     gate — so "Australia look great on 4 noisy games" can't print a huge edge.
     We already have shrink_blend in peripheral_markets; lift it to a shared
     helper and apply to value legs.

  Net effect: the model still fires when it sees a believable, sample-backed,
  sharp-anchored edge ("if you do see a true edge great lets go") but can no
  longer smash in a 68% EV longshot. Calibrated, not timid.

  TESTS: a regression test that the exact Australia-v-USA shape (model 0.45 vs
  market implied 0.27, ~+68% EV) is REJECTED, plus that a believable +6% solid
  edge still passes. Lock the contract so it can't regress.

==============================================================================
PROBLEM 2 — Model only picks win/draw/goals; what about other markets?
==============================================================================
CURRENT: the value board (betting.py _all_value_markets) only scans the 5
markets in market_defs: home_win, draw, away_win, over_2_5, btts. The full
30-market sheet (derive_markets) is priced but NEVER scanned for value.

THE FIX: widen the value scan to the rich sheet markets we already price off
the same Dixon-Coles grid — Double Chance, Draw No Bet, Over/Under 1.5 & 3.5,
team totals, clean sheet, win-to-nil, correct score (top cells). Each gets the
SAME calibration gate from Problem 1, and the same reliability tiering. Markets
without a real book line stay informational only (no fake EV), exactly as the
peripheral corners/cards markets already are. This gives the model more honest
ways to find an edge ("if it thinks it will win it's also doing other things")
without loosening the discipline.

==============================================================================
PROBLEM 3 — Track record "poorly formulated", needs filters
==============================================================================
CURRENT STATE (the confusion):
  - /predictions  -> "Prediction Track Record" (every single value pick),
                     labelled "My Picks" in the nav (WRONG label).
  - /model-picks  -> daily auto multis + their ROI. NOT IN NAV AT ALL.
  - /my-picks     -> user's OWN picks vs the model (local). NOT IN NAV.
  - HistoryTable has ZERO filters: flat chronological list, no way to slice
    by result / market / confidence tier / won-lost.

THE FIX:
  A) Add a filter/segment bar to the track record (HistoryTable): filter by
     Result (all / won / lost / pending), by Market (1X2 / O-U / BTTS / ...),
     and by Confidence tier (solid / speculative). Plus a sort (newest / best
     EV / biggest win). Pure client-side over the data we already return.
  B) Add a summary strip that updates with the active filter (n picks, hit
     rate, ROI for the current slice) so filtering actually informs a decision.
  C) Fix the naming so the three pages stop colliding (see Problem 4).

==============================================================================
PROBLEM 4 — Mobile nav missing Model Picks + My Picks
==============================================================================
CURRENT mobile nav (BottomNav):
  Primary tabs: Matches, Live, Value, Acca, Bracket.
  "More" sheet -> Tracking group: Report Card, "My Picks" (=/predictions),
                  Match 3 Watch. /model-picks and /my-picks ARE NOT LINKED.

THE FIX (rename for clarity + add the missing links):
  Tracking group becomes:
    - Model Picks   -> /model-picks   (the daily auto multis)         [NEW LINK]
    - Track Record  -> /predictions   (was mislabelled "My Picks")    [RENAMED]
    - My Picks      -> /my-picks      (your own picks vs the model)    [NEW LINK]
    - Report Card   -> /performance   (accuracy + calibration)
  Drop "Match 3 Watch" out of Tracking into Tournament (it's a tournament view).
  This removes the naming collision and surfaces every picks surface on mobile.

==============================================================================
BUILD ORDER (each shippable + tested independently)
==============================================================================
  1. P1 calibration guardrails (backend, multi_picker + value board + shared
     shrink helper) + regression tests. ← highest value, do first.
  2. P2 widen value markets (backend) + tests.
  3. P4 nav rename/add links (frontend, tiny, low-risk).
  4. P3 track-record filters + summary strip (frontend).
Each lands as its own commit, full test run, deploy.

OPEN QUESTIONS FOR YOU (before I build):
  Q1. Upper EV cap: is 25% the right ceiling, or do you want it tighter (e.g.
      15%) given the WC sample is small and noisy? Tighter = fewer, safer picks.
  Q2. Model multis: keep auto-publishing them, or do you want the gate so
      strict that on a quiet slate it publishes ZERO ("no bet" is a valid day)?
      I'd recommend yes — a no-bet day beats a forced longshot.
  Q3. For "My Picks" (your own vs model) — keep it, or is that page noise you'd
      rather drop from nav and fold into the match page?
