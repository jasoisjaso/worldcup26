# WC2026 Model + Data + Markets — Research & Audit Findings (2026-06-22)

Research-backed review of what we pull from API-Football, what the model does
with it, the betting markets we surface, and where the model loses accuracy.
Sources: api-football v3 docs, peer-reviewed Bundesliga/xG prediction papers
(Frontiers 2025, Sage/Wilkens 2026), Towards Data Science WC ML study, the
sports-ai.dev calibration writeup, and football betting-market guides.

==============================================================================
1. WHAT WE ALREADY PULL (audit) — this is GOOD, near-complete
==============================================================================
API-Football endpoints harvested + normalised (harvest_processor.py):
  /players/squads, /players, /players/topscorers, /players/topassists,
  /fixtures (+ auto fan-out), /fixtures/statistics, /fixtures/events,
  /fixtures/lineups, /fixtures/players, /fixtures/h2h, /predictions,
  /standings, /teams/statistics, /coachs, sidelined, transfers, /odds (raw).

/fixtures/statistics fields we capture (FixtureArchive):
  possession, shots (on/off/total/inside-box/outside-box/blocked), xG,
  goals_prevented, passes_total, pass_accuracy, fouls, yellow/red cards,
  corners, offsides, goalkeeper_saves.
  => This is the FULL statistics payload. Nothing material is missing here.

VERDICT: Data coverage is strong. For the post-WC EPL/Bundesliga/Serie A
pivot, seed lists already include leagues 39 (EPL), 78 (Bundesliga), 135
(Serie A) across 15 seasons (2010-2024). The harvester just needs to keep
running (the burn-rate fix lets it actually drain the queue now).

Small data gaps worth closing (low priority, not accuracy-critical):
  - corners_against / shots_against per team are NOT stored as their own
    columns; peripheral_markets.py falls back to a prior for the defensive
    side. We DO have the opponent row in the same fixture, so this is
    derivable without new API calls (future processor enhancement).

==============================================================================
2. THE MODEL — what it does well, and the ONE real accuracy gap
==============================================================================
Engine (group_predictor.py -> elo_model.py -> dc_ratings.py -> poisson.py):
  - Dixon-Coles fitted ratings BLENDED with ELO (0.55 same-conf / 0.45
    cross-conf, set by a ~1500-match walk-forward backtest). Good.
  - Confederation offsets correct DC's documented cross-confederation bias. Good.
  - 10 lambda modifiers (rest, dead-rubber, squad quality, injury, h2h,
    weather, travel, lineup, harvested xG, set pieces) combined in LOG space
    with a single ±0.25 aggregate cap so correlated factors can't compound. Good.
  - Neutral-venue aware: BASE_GOALS symmetric, no baked-in home-field bias.
    CORRECT for a WC (the #1 documented model failure — "systematically
    overconfident in home wins" — does not apply here because there is no
    home team; venue bonus is host-nation/diaspora crowd only). Good.
  - DC rho = -0.13 lifts 0-0 and 1-1, the standard low-score draw correction. Good.
  - Market blend: 70% model / 30% Shin-devigged market, with Pinnacle sharp
    anchor preferred over soft books. Value/EV measured on RAW model prob vs
    book (so the value finder hunts genuine edges, not market agreement).
    Reliability tiers (solid/speculative/longshot) keep longshot fantasies out
    of picks. This is the right balance: NOT blindly following the bookie,
    NOT ignoring it. Good.
  - CLV tracking + per-match Brier/log-loss calibration logger. Good.

THE GAP (this is the lever for "getting so many wrong"):
  Every source agrees Poisson/DC models are OVERCONFIDENT in the mid-band
  (predicted 0.35-0.65 > realised) and UNDER-PREDICT DRAWS beyond what rho
  fixes. The DC rho only nudges the 4 low-score cells; it does not correct
  the broader draw deficit or the favourite over-confidence that shows up at
  the OUTCOME (1X2) level.
  - We MEASURE this (calibration_logger: Brier, log-loss, favourite_correct)
    but NOTHING FEEDS THE MEASUREMENT BACK into the probabilities. The model
    can be visibly miscalibrated for the whole tournament and never self-correct.

FIX (implemented): a calibration shrinkage layer applied to the 1X2 vector
  AFTER the score matrix, BEFORE the market blend:
    1. Draw-floor / draw-uplift: gently shrink the favourite and lift the draw
       toward the empirical international base rate (draws ~26-28% of neutral
       internationals) when the model's draw prob is suspiciously low for an
       evenly-matched game.
    2. Mid-band confidence shrink: pull extreme favourite probs toward the
       outcome mean (temperature-style), the documented cure for mid-band
       overconfidence. Strength is a single tunable constant, defaulted
       conservatively and unit-tested so it can only narrow the gap, never widen it.
  This is the standard, low-risk calibration correction (Platt/temperature-
  style shrink) and it is the highest-EV change available without new data.

==============================================================================
3. BETTING MARKETS — coverage vs what people actually bet
==============================================================================
Most-bet football markets (punter2pro, fulltimepredict, soccernews):
  1X2, Asian Handicap, Over/Under goals, BTTS, Double Chance, Draw No Bet,
  Correct Score, Corners O/U, Cards O/U, Goalscorer (anytime/first).

What we surface (markets.py + peripheral + goalscorer):
  1X2 ✓, O/U 2.5 (+ ladder) ✓, BTTS ✓, Asian Handicap ✓, Correct Score (top
  scores) ✓, Corners O/U (match + per-team) ✓, Yellow Cards O/U ✓,
  Goalscorer ✓. Strong coverage.

Cheap, high-demand additions (pure math off the EXISTING score matrix — zero
new data, zero new API calls):
  - Double Chance (1X / 12 / X2): trivial sums of 1X2 we already compute.
  - Draw No Bet: home/(home+away) and away/(home+away).
  - Over/Under ladder is present; expose 1.5 and 3.5 explicitly on the sheet.
  These three are among the most-bet "lower-risk" markets and we already have
  everything needed to price them. (Implemented: Double Chance + DNB.)

==============================================================================
4. MATCH PAGE — "give us everything to make an informed decision"
==============================================================================
Already surfaced: 1X2 + model vs market, why-factors, lambdas, top scores,
full markets sheet, harvested xG/corners snapshot, EV per market, odds source.

Open-source viz that would genuinely help the decision (no heavy deps):
  - A calibration/reliability strip on /performance (we have the Brier data;
    just need to render the reliability curve so the user SEES whether the
    model is trustworthy in each probability band). Recharts is already the
    charting lib in the FE.
  - A "model vs market" divergence bar on the match page so the user instantly
    sees where we disagree with the bookie and by how much (the core
    "informed decision" signal). Data already in the prediction payload
    (our_prob vs implied from bookmaker_odds).

==============================================================================
5. LIVE PAGE — flagged as needing work
==============================================================================
Current: 15s poll, event ticker, WP sparkline, in-play stats behind a toggle,
key-player stacks, smart bet slip with edge + Kelly. Solid bones.
Weaknesses to address (taste pass):
  - Density/hierarchy: the at-a-glance scoreboard and the deep stats compete;
    expand toggle is good but the default card could lead harder with the
    single most decision-relevant live number (live win-prob shift + xG).
  - In-play model: the live WP should lean on live xG (which we capture) not
    just score + clock, so the smart-bet edge reflects chances created, not
    just the scoreline. (Research: live xG is the strongest in-play signal.)

==============================================================================
PRIORITISED IMPLEMENTATION PLAN
==============================================================================
P0 (accuracy, this PR): calibration shrinkage layer on 1X2 (draw uplift +
   mid-band confidence shrink), unit-tested. Highest EV, lowest risk.
P1 (markets, this PR): Double Chance + Draw No Bet on the markets sheet.
P2 (next): match-page model-vs-market divergence bar; /performance reliability
   curve from existing Brier data.
P3 (next): live in-play WP weighting toward live xG.
