# What we can learn from the DataCamp WC prediction work

Two main pieces examined:

1. **Farnschläder, June 2026, DataCamp tutorial** — full MLOps pipeline,
   10 models on 347-match holdout, XGBoost winner. Repo:
   github.com/tomppa999/MLOps_FootballWCPredictor. Dashboard:
   wc2026-predictions.streamlit.app
2. **Joury, Towards Data Science** — 11 models on 358 matches, four
   different champions. Argues model **disagreement** is the most
   valuable output, not the picks themselves.

## What CONFIRMS we are on the right track

These are things both authors do that match our existing build, so we
do not need to change them:

- **Predicting goals via Poisson is the right base.** Both use it.
  Farnschläder explicitly says "predicting goals rather than results
  is what makes everything later possible". This is what
  `backend/models/poisson.py` already does via Dixon-Coles.
- **Elo difference is THE feature.** Farnschläder finds it ~100x more
  influential than the next strongest. We already use Elo as one of
  two rating systems (alongside DC). Don't over-engineer.
- **Top models cluster within noise.** Farnschläder's top 5 are
  within 0.0011 RPS. Conclusion: ceiling is set by data quality, not
  algorithm choice. Switching DC for XGBoost would be ~zero gain.
- **Deep nets are wrong tool at this sample size.** Both authors find
  LSTMs/CNNs/MLPs lose to classical methods on ~7,000-match data.
  Stay where we are.
- **NB barely departs from Poisson** (Joury found alpha ~0.008 fit).
  No reason to add a negative-binomial layer.

## Strong NEW ideas worth lifting

### Idea 1: Surface model disagreement as a confidence signal

**Joury's core insight:** "A single model hands you a single answer
and no sense of how much it hinges on the dozens of choices buried
inside it ... change any one of them and the answer can move by
double digits."

His Spain v Morocco table is the killer demo: 11 models, Spain win
probability ranges 25-69%. XGBoost calls a 64% DRAW. The disagreement
is the signal.

We already run TWO model views (Dixon-Coles + Elo) and combine them.
We already have a `model_uncertainty` field on `MatchPrediction`
("confident" / "moderate" / "uncertain") that drives the
`DataProvenance` caveat line. But we don't expose the underlying
numbers.

**Proposal:** add an optional "two takes" disclosure on the match
page. Below the verdict block, a small line:

> Dixon-Coles says Brazil 60%, draw 30%, Scotland 10%.
> Elo says Brazil 65%, draw 25%, Scotland 10%.
> They mostly agree, so the verdict is high-confidence.

Or when they don't agree:

> Dixon-Coles says Scotland 25%, but Elo says 11%.
> The two methods disagree, so treat the verdict as lower-confidence.

Cost: ~1h frontend, the data is already on the payload. Direct
visibility into the model_uncertainty field we already calculate.

### Idea 2: Held-out RPS in the trust strip

Farnschläder benchmarks on 347 matches from 2022 WC + 6 other major
tournaments (EURO, AFCONs, Copa, Asian Cup, Gold Cup). He publishes
his RPS as **0.18289** for XGBoost vs **0.22872** for the no-feature
baseline.

Our trust strip currently shows hit rate on our PUBLISHED picks. That
is a biased sample because we only publish +EV picks. The honest
calibration number is RPS on every prediction we make, evaluated
when it lands.

**Proposal:** backtest our DC+Elo blend on 2018 and 2022 WCs + the
2024 EURO. Compute RPS. Publish that as a fourth metric in the trust
strip alongside hit rate, sample, ROI, CLV. Something like:

> Calibration (RPS): **0.183** on 245 backtest matches

The RPS scale is industry-standard. A number near 0.18 puts us in
the same band as Farnschläder's XGBoost, which is the right framing
for credibility.

Cost: ~3h backend (backtest harness + RPS computation), ~30min
frontend trust-strip extension. Sample of test matches is already in
the archive.

### Idea 3: Show market consensus as a sanity check

Joury keeps "the market" as one of his 11 models and notes the market
agrees with Spain alongside Elo / Poisson / NB / Logistic / KNN /
PageRank. The market is itself a strong opinion. We already de-vig
the soft books and use sharp anchors — we have the data.

**Proposal:** on the verdict block, add a one-liner under the explain:

> Market consensus: Brazil 75%, draw 17%, Scotland 8%.

This is implicit in our edge calculation but never spelled out. For
a casual it reads as "here's where everyone else is" alongside our
own number. For a sharp it's a direct comparison.

Cost: ~30min frontend. Data already on the payload.

### Idea 4: Faster refit during the tournament

Farnschläder retrains **bi-hourly** during the tournament on GCP. We
refit DC every 3 hours (180 minutes) per the feeds list. After a
brutal blowout or upset, faster refit cadence captures the momentum
shift sooner.

Worth checking: how long does our DC refit actually take? If under
5 minutes, dropping to bi-hourly (120 minutes) is essentially free.
If it's 20+ minutes, we should know that before considering it.

Cost: zero if the refit is cheap, otherwise needs profiling first.

### Idea 5: Held-out tournament simulator coverage

Farnschläder runs Monte Carlo with **10,000 tournament sims** per
predicted state. We have a `tournament_sim` feed but I haven't
verified what it actually projects. Joury simulates the full 48-team
12-group format with top 2 + 8 best thirds advancing — the new 2026
rules. Worth confirming our simulator handles best-third
combinatorics correctly.

If yes: a "your team's path" view per country — "Scotland have a 12%
chance of qualifying for the round of 32 if they hold to a draw
here" — is a strong fan-engagement feature. The DataCamp piece
calls this out as the main value of the goal-level model. Direct
tie-in to the "Backing X" proposal we just wrote.

Cost: depends on what the simulator already does. Need to read
`backend/data/tournament_sim.py` or wherever it lives before scoping.

## What we should NOT copy

- **Switching to XGBoost.** Wins by 0.0011 RPS on holdout. Not a
  meaningful win for the engineering churn. Dixon-Coles is already
  good enough and stays interpretable.
- **A bigger MLOps stack on GCP.** We're already running DC fits
  in-process every 3h. The pipeline overhead is solved.
- **Predicting tournament winner with high confidence.** Joury's
  whole point is that 11 models crowned 4 different champions. We
  should show the simulation distribution, not a single prediction.

## Priority order if you pull the trigger on any of these

1. **Idea 3** (market consensus one-liner) — 30 min, zero risk,
   immediate trust-strip-grade content addition.
2. **Idea 1** (two takes disclosure) — 1 h, surfaces the
   `model_uncertainty` we already compute.
3. **Idea 2** (held-out RPS in trust strip) — 3-4 h, sharpest
   credibility upgrade we could ship.
4. **Idea 5** (verify + extend tournament sim) — depends on what's
   there. Read first.
5. **Idea 4** (faster DC refit) — only if profiling shows it's
   essentially free.

Total Ideas 1+2+3 = about 5 hours. Could ship as a single "model
transparency" commit on top of the voice work.

## How this slots in

These ideas slot in BEFORE the "Backing X" feature (the
team-loyalty proposal). Ideas 1 and 3 together would land
particularly well as preparation for the Backing X cards, because
Card 2 (the smarter bet) reads stronger if the user can see model
agreement and market context next to the verdict.

If you want me to ship one of these now, Idea 3 (market consensus
one-liner) is the smallest possible bite and the closest in spirit
to the voice we already shipped this afternoon.
