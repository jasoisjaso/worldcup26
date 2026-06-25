# Model-picks revamp — research notes (2026-06-26)

The /acca?tab=model picks were producing "wild shit": 3-leg multis at 7-8% landing
chance with triple-digit EV, stacking three contrarian outcomes on the same matchday.
This file is the math behind the new picker.

## What was wrong in the old picker (`backend/api/routes/betting.py:get_acca`)

- Pure greedy raw-EV maximisation per leg-count. `total_ev = combined_prob × combined_odds − 1`, kept the max.
- Candidate filter let in per-leg EV up to 150% (`v["ev"] <= 1.5`) and odds up to 8.0.
- No combined-probability floor. A slip with 1% landing chance and +200% EV beats a 30%-landing +20% EV slip.
- Diversification only blocked same beneficiary team. Two unrelated underdog upsets on the same matchday were free to stack.
- Naive product of `model_prob` per leg. Same-match correlation handled in `multi_analyzer.analyze_multi` but the picker never used it.
- Live example caught on 2026-06-26: Japan-Sweden O2.5 + Egypt-Iran (Iran win, 31.9% model) + Cape Verde-Saudi Arabia (Draw, 37.6% model). Combined prob 7.87%, +93.5% EV. Each leg defensible alone; the multi is a near-miss machine.

## Research basis

### Whelan (2026), *Compounding an Edge? Expected Utility and the Puzzle of Parlay Betting*

The key result: even when the bettor has an edge, expected utility maximisation requires
short parlays. The geomean-per-leg probability threshold to prefer N-leg over (N-1)-leg
under CRRA utility:

| Prefer this size over the previous | Geomean p threshold |
|---|---|
| 2-leg over 1-leg | 0.335 |
| 3-leg over 2-leg | 0.526 |
| 4-leg over 3-leg | 0.634 |
| 5-leg over 4-leg | 0.703 |
| 6-leg over 5-leg | 0.750 |

These thresholds are nearly independent of risk-aversion (σ ∈ [0.2, 4]) and edge size
(e ∈ [0.005, 0.05]). For three agents with widely different edges, they agree on the
optimal parlay length over ~94% of the probability interval.

**Implication for our picker:** for each slip size N, refuse to surface the slip if
its geomean per-leg model probability is below the table value. A 3-leg slip with
geomean p = 0.42 (the Iran-upset slip above) is mathematically worse than the same
2-leg slip even before considering vig.

### Uhrín, Šourek, Hubáček, Železný (2021), *Optimal Sports Betting Strategies in Practice*

> "A worse model with a better strategy can easily outperform a better model with a worse strategy."

- Adaptive fractional Kelly is the most suitable strategy across horse racing, basketball, soccer.
- Quadratic Kelly ≈ MPT with γ = ½: the geometric mean is approximately the arithmetic mean minus ½ of variance.
- Raw EV-max as an *objective* is dominated by fractional-Kelly and Markowitz Sharpe in their experiments.

**Implication:** the new "Balanced" objective uses `prob × log(odds × prob)`
(Kelly's log-utility on a single binary bet), which is a much better proxy for
long-run growth than raw EV.

### Predictology — *Bet Builders vs. Single Bets*

- Bet builders / SGPs carry 20-25% margin vs 4-6% for singles.
- Negative correlation between legs is the rare +EV hotspot.
- Long-term bankroll growth: high-volume singles beat any multi strategy.

### Unabated — *When Maximising EV Don't Be Fooled By PV*

- Perceived value: "boosted" parlays often -10 to -16% EV when priced.
- Adding a leg more than doubles potential payout, which novices read as a money glitch.
- Variance crushes under-bankrolled bettors; with an edge, "prioritise EV without major swings."

## New picker design

### Objectives

| Objective | Score | Floor (geomean p) | Max legs | Per-leg odds cap | Per-leg EV cap |
|---|---|---|---|---|---|
| **Solid** | `combined_prob` | 0.50 | 3 | 3.0 | 0.20 |
| **Balanced** | `prob × log(odds × prob)` | Whelan-table by size | 4 | 4.0 | 0.25 |
| **Bold** | `combined_prob × combined_odds − 1` | Whelan-table by size | 3 | 4.5 | 0.30 |

**Solid** is for the user who wants the multi to *land*. It maximises win probability
and never takes more than 3 legs even if a 4-leg is mathematically better.

**Balanced** is the default. The log-utility score is what Kelly's criterion maximises
on a single binary bet and is roughly geomean-of-wealth growth. It penalises low-prob
high-EV outliers naturally.

**Bold** is for the user who explicitly wants to chase value. Even here, Whelan's
result caps us at 3 legs (per-leg probability >= 1/3 to justify going from 1-leg to
2-leg, so 4-leg requires geomean p >= 0.63 which our candidate pool rarely contains).

### Common filters

- Per-leg `model_prob` >= 0.30. Below that, the per-leg estimate is too noisy to stack.
- Per-match grade must be `core` (the existing pick guardrail).
- Per-leg odds and per-leg EV caps as in the table.

### Diversification (applied during combo enumeration)

- At most 2 legs per matchday.
- At most 2 legs per market category (1X2, totals, BTTS).
- No two legs benefiting the same team (extended: covers `home_win`, `away_win`, and
  `home_*`/`away_*` team totals).

### Combined probability

Use `multi_analyzer.analyze_multi` to compute combined probability with same-match
correlation handled off the score grid. Cross-match legs multiply; same-match legs
intersect on the grid. The old code was naive product.

### Compound margin (display only)

For honesty, show the user the slip's compound margin: how much vig the bookmaker
collects on this multi versus on each leg singly. Formula:

```
per_leg_margin = (sum(1/odds_i over all outcomes of leg_i) − 1) / sum(1/odds_i)
compound_margin = 1 − prod(1 − per_leg_margin)
```

We display the simpler form:

```
compound_margin ≈ 1 − (prod(model_prob_i × odds_i)) ^ (1/N)
```

which is roughly the geomean of "slip is at a Y% effective vig per leg".

### Rationality verdict (Whelan)

For each surfaced slip, attach:

- `whelan_min`: the geomean p threshold for this slip size to be optimal.
- `geomean_per_leg_prob`: the slip's geomean of per-leg model probabilities.
- `rationality_verdict`: `"optimal_size"` if cleared, else `"smaller_better"`.

In the UI, slips marked `smaller_better` are still shown for transparency but with
a yellow chip saying "A shorter version of this slip would be better long-run."

## What this fixes

- The Iran-upset + CV-SA-draw 3-leg slip from 2026-06-26: geomean p = 0.42, below
  Whelan's 0.526 → flagged `smaller_better`, the picker would prefer the 2-leg
  (Japan-Sweden O2.5 + best singleton; geomean p ~= 0.55).
- 4 and 5-leg slips with one or two ~30% legs no longer score above the floor.
- The Balanced objective dampens the longshot bias of pure EV-max.
- Diversification per matchday + per market category stops "5 overs in 5 same-day games" stacks.

## What this does NOT fix

- The model's per-leg probability estimate on thin-sample minor nations. The shrink
  and `_grade_pick` already handle the most extreme cases (the +68% Aus-USA loss),
  but improving the underlying lambda estimates is a separate model upgrade.
- Negative-correlation hunting on bet-builder lines. Mentioned in Predictology as the
  rare +EV hotspot; out of scope for this revamp because it requires a corner/card
  model we don't validate yet.
