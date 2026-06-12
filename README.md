<div align="center">
  <img src="docs/logo.svg" width="64" alt="WC26 Predictor logo" />
  <h1>WC2026 Predictor</h1>
  <p>Data-driven match predictions for the 2026 FIFA World Cup</p>
  <a href="https://wc26.tinjak.com"><strong>wc26.tinjak.com →</strong></a>
  &nbsp;&nbsp;
  <img alt="72 tests passing" src="https://img.shields.io/badge/tests-72%20passing-22c55e?style=flat-square" />
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3b82f6?style=flat-square" />
  <img alt="Next.js 14" src="https://img.shields.io/badge/next.js-14-ffffff?style=flat-square" />
</div>

---

## Screenshots

| Matches + predictions | Match analysis |
|---|---|
| ![Matches page](docs/screenshots/matches.png) | ![Match analysis](docs/screenshots/match-analysis.png) |

| Value board | Multi builder |
|---|---|
| ![Value board](docs/screenshots/value-board.png) | ![Acca builder](docs/screenshots/acca.png) |

---

## What it does

**Match predictions** — Win, draw, and loss probabilities for every group stage match. Powered by a Dixon-Coles model blended with ELO ratings, with context adjustments for altitude, rest days, squad quality, and tournament situation.

**Value board** — Compares model probabilities against live odds from Bet365, Sportsbet, and Unibet. Surfaces markets where the bookie is underpricing a team. Filtered by matchday and market type.

**Multi builder** — Builds 3 to 5 leg multis from value picks. Filters out same-match doubles, caps odds at 8.0, and selects the combination with the highest expected value.

**Score matrix** — Full 9x9 scoreline probability grid per match. Most likely final scores ranked by probability.

**Set piece estimates** — Expected corners and yellow cards per game, calibrated to WC group stage data.

**Group tables** — Live standings across all 12 groups.

**Prediction tracker** — Pre-kickoff picks logged automatically. Settled after results come in with accuracy tracking.

**Match 3 watch** — Flags final group games with rotation or dead-rubber risk.

---

## Model

### The problem with a naive approach

Most public WC predictors either use raw ELO or a basic Poisson model. Both have the same failure mode: cross-confederation comparisons. An ELO of 1750 in CAF is not the same as 1750 in UEFA. Algeria built their defensive ELO rating by shutting out teams like Equatorial Guinea and Comoros. Running that number directly against Argentina produced Algeria with a 33% chance of winning — which is nonsense. The whole model architecture is designed around fixing that class of problem.

---

### Layer 1: Dixon-Coles MLE

The base layer is a [Dixon-Coles](http://www.math.su.se/matstat/reports/seriea/2000/rep2/report.pdf) model fitted on ~6 years of international results. Dixon-Coles extends the basic Poisson model by adding a low-score correction factor (rho) that pulls probability mass from 1-0 and 2-0 results toward 0-0 and 1-1, which are systematically under-predicted by independent Poisson.

Each team gets two parameters:
- `alpha` — attacking strength (how many goals they score relative to expectation)
- `beta` — defensive strength (how few goals they concede relative to expectation)

These are fitted by maximum likelihood. 47 WC2026 teams had enough international data to fit.

**Why we don't use pure DC:** DC parameters are calibrated within-confederation. Algeria's beta is extremely negative (strong defender) because they were measured against CAF opposition. Running that against Argentina's alpha directly inflates Algeria. This is a known problem with any club-season model applied across leagues, just applied here across confederations.

---

### Layer 2: Confederation-aware ELO blend

We apply a blending weight based on confederation distance:

```
Cross-confederation (offset diff > 50):  45% DC + 55% ELO
Same-confederation:                       55% DC + 45% ELO
```

These weights were lowered from an earlier 50/75% DC after the walk-forward backtest
(see [Validation](#validation)) showed the DC/ELO blend optimum on ~1500 out-of-sample
internationals is a flat 40–60% DC — the old weighting over-trusted DC, the component
that is least reliable cross-confederation.

ELO ratings are sourced from [eloratings.net](https://www.eloratings.net) — they encode real WC tournament performance including cross-confederation matches, so they provide a sensible anchor when DC parameters are unreliable.

Confederation base offsets (applied to ELO before comparison, derived from historical WC performance):

| Confederation | Range | Notes |
|---|---|---|
| UEFA | +56 to +117 | Scotland to France |
| CONMEBOL | +42 to +104 | Paraguay to Argentina |
| AFC | +7 to +18 | Iraq to Japan |
| CONCACAF | -27 to -11 | Haiti to Mexico |
| CAF | -40 to -16 | Cape Verde to Morocco |
| OFC | -171 | New Zealand |

**Before fix:** Brazil 37% / Morocco 38% (broken — Morocco's DC alpha inflated from AFCON wins)
**After fix:** Brazil 58% / Morocco 20% — which aligns with bookmaker odds and common sense

---

### Layer 3: Context adjustments

A set of context modifiers is applied on top of the blended lambda values. The
multiplicative modifiers (rest, dead rubber, squad quality, injuries, head-to-head,
weather, travel, lineups, club xG/set pieces) are combined **in log space with a single
aggregate cap of ±0.25** (≈ 0.78×–1.28× total), so several correlated hand-tuned factors
can never compound to an extreme lambda the score matrix was not calibrated for. The
additive altitude bonus is applied after the multiplicative stack so its calibrated
goal magnitude is preserved.

#### Altitude

Mexico City (2240m) and Guadalajara (1522m) reduce aerobic performance for unadapted teams. Studies of WC 1970 and 1986 (both played at altitude) show sea-level teams concede significantly more goals per game at these venues. Teams historically based at altitude (Colombia, Ecuador, Mexico, Bolivia, Peru) get a bonus.

```
Mexico City:  +0.12 goals (additive to both teams' lambdas)
Guadalajara:  +0.06 goals
```

#### Rest days

Teams with fewer days since their last match are slightly disadvantaged. WC group scheduling gives 3-5 days between games. We apply a ±2%/day multiplier on lambda, capped at ±6%.

```
Rest advantage of 2 days:  ×1.04 for rested team, ×0.96 for fatigued team
```

#### Dead rubber (MD3)

In matchday 3, a team that is already qualified (6 points) or already eliminated (0 points, with no path to qualification) is at risk of rotating the squad or losing concentration. Historical WC data shows dead rubber teams underperform expectation. We apply a 0.87 lambda multiplier for confirmed dead rubbers.

#### Squad quality

Transfermarkt market values are used as a proxy for squad depth. A 10x squad value gap (e.g., England €1.1B vs Haiti €30M) shifts lambdas by up to ±8% via log-ratio scaling:

```python
adj = 0.08 * log10(home_val / away_val)  # capped at ±0.08
```

This prevents underdogs from being treated as zero-strength and captures squad depth effects that ELO (which only tracks results) misses.

#### Injuries (live — activates automatically)

An API-Football integration queries current injury data for all 48 squads. When a team is missing a key attacker or defender, their lambda is adjusted proportionally. The module returns 1.0 until WC2026 fixture data is available in the API, then auto-activates.

---

### Win probabilities

The blended, context-adjusted lambda pair is fed into a 9x9 Dixon-Coles score matrix. All probabilities (win/draw/loss, over/under 2.5, BTTS, Asian handicap, top scores) are derived from the same matrix.

---

### Form adjustment

Last 5 results are weighted (oldest = 0.1, most recent = 0.3) and applied as a lambda delta, clamped to ±0.10:

```
delta = weighted_sum(W=1, D=0, L=−1)  →  clamped to [−0.10, +0.10]
```

---

### Expected value

```
EV = (model_probability × decimal_odds) − 1
```

Positive EV means the model thinks the bookie is underpricing the outcome. Odds are the median of Bet365, Sportsbet, and Unibet via The Odds API. The market is de-vigged with **Shin's method** (not naive proportional normalization), which corrects the favourite-longshot bias in the tails where the value board operates, and the model is blended 70/30 with that fair line on both 1X2 and Over/Under 2.5.

---

### Kelly stake sizing

Quarter-Kelly is used for stake sizing:

```
full_kelly  = (b × p − q) / b
quarter_kelly = full_kelly × 0.25
```

Where `b = decimal_odds − 1`, `p = model probability`, `q = 1 − p`. Quarter-Kelly is more conservative than full Kelly and better suited to a small sample like a group stage where variance is high. Every stake is additionally hard-capped at 5% of bankroll, because Kelly is acutely sensitive to an over-estimated edge from an only-approximately-calibrated model.

---

### Same-game multi (SGM) correlation

When combining markets from the same game, a correlation table adjusts the naive product probability. Home win + over 2.5 goals are positively correlated (factor 1.15). Draw + BTTS are negatively correlated (factor 0.85).

---

## Why we made the decisions we made

| Decision | Why |
|---|---|
| Dixon-Coles over pure Poisson | DC's rho correction catches the low-score bias; 0-0 and 1-1 are consistently undervalued by Poisson alone |
| ELO anchor for cross-confederation | DC parameters are within-confederation artefacts; ELO encodes actual WC results including cross-conf games |
| DC/ELO blend leans on ELO (≈0.5 DC) | Backtest on ~1500 OOS internationals puts the optimum at a flat 40–60% DC; the earlier 50–75% DC over-trusted the less-reliable component cross-confederation |
| Additive altitude (not multiplicative) | Goals per game at altitude goes up for both teams. Additive to both lambdas captures this; a pure team-advantage factor doesn't |
| 0.87 dead rubber factor | Fitted from WC 2014 and 2018 MD3 data — qualifying teams outscored their expected goals by ~13% and eliminated teams underscored by ~13% |
| Transfermarkt values as squad proxy | Transfermarkt captures squad depth, age profile, and club competition level in a single number. The log-ratio is compressed so it never dominates |

---

## Validation

The goal model is validated with a walk-forward backtest (`backend/eval/backtest.py`) that
replays ~1500 out-of-sample competitive internationals — refitting Dixon-Coles at each
cutoff and scoring **ordinal RPS, log-loss, Brier and calibration (reliability / ECE)**
against an Elo and a climatology baseline. It is the gate for any change that touches a
predicted probability. Run it with `python -m backend.eval.backtest`. Findings that shaped
the current model:

- **Time-decay ξ** lowered from 0.00325 to **0.0018/day** — the club-tuned value was ~3×
  too aggressive for sparse international data (DC RPS 0.1727 → 0.1696).
- **DC/ELO blend** shifted toward ELO (see Layer 2) — the blend optimum is a flat 40–60% DC.
- The **MD1 rho relaxation was a bug** (a less-negative rho shrinks the 1-1 draw cell and so
  produces *fewer* draws, the opposite of intent) and was removed.
- The **fixed-sum ELO→λ total** looks like a flaw, but replacing it with a "total-from-DC"
  decomposition *regressed* both 1X2 and Over/Under, so it was kept — the pin toward the
  ~2.6 league-average total acts as useful shrinkage of a noisy DC total.
- The model is already well-calibrated (ECE ≈ 0.03, optimal temperature ≈ 1.0), so **no**
  post-hoc calibration layer was added.

Live predictions are scored the same way: every upcoming match's full distribution is
snapshotted pre-kickoff, and `/history/calibration` reports RPS / Brier / log-loss /
reliability over finished matches — unbiased by the +EV pick selection that `/history/stats`
is conditioned on.

## What we know we're missing

Honest accounting of the gaps that remain:

**Pi-ratings / GBM ensemble** — Constantinou and Fenton's pi-ratings track goal differences and maintain separate home/away ratings; state-of-the-art models (CatBoost + pi-ratings, Razali et al. 2024) report RPS ≈ 0.1925. These offer the largest published gains but are large-effort and overfitting-prone on sparse international data, so they wait until the backtest proves the cheaper fixes first.

**Goalkeeper form** — A tournament-form goalkeeper (Diogo Costa saving three penalties at WC2022) can independently shift outcomes by 15-20%, bypassing the goal-based model. No public API provides real-time GK form ratings.

**Calibration of the context modifiers** — Travel distance, weather, set-piece xG, and head-to-head are all live now, and their combined effect is capped (±0.25 in log space) so they can't compound. But their individual magnitudes are hand-tuned, not backtested against labelled outcomes — there is no historical injury/lineup/weather feed to fit them against, so they remain plausible priors rather than validated parameters.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router, SSR) |
| Backend | FastAPI + APScheduler |
| Database | SQLite via SQLAlchemy |
| Odds feed | The Odds API |
| ELO ratings | eloratings.net (scraped, 24h cache) |
| Form data | martj42/international_results (6h cache) |
| Squad values | Transfermarkt (static dict, 48 teams) |
| Injury data | API-Football (live when WC fixtures available) |
| Deployment | Docker on VPS behind Nginx Proxy Manager |
| Tests | pytest (72 tests, pure logic) |
| Validation | walk-forward backtest (`backend/eval/backtest.py`), RPS/Brier/log-loss |

---

## Running locally

```bash
# Backend
cd backend
pip install -r requirements.txt
THE_ODDS_API_KEY=*** uvicorn backend.api.main:app --reload

# Frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Set `THE_ODDS_API_KEY` in your environment for live odds. Without it, predictions still run but the value board will show no live markets.

```bash
# Tests
cd /path/to/repo
python -m pytest backend/tests/ -v

# Walk-forward backtest of the goal model (RPS / log-loss / Brier / calibration)
python -m backend.eval.backtest                 # fast default
python -m backend.eval.backtest --xi-sweep      # also sweep the time-decay constant
```

---

## Predictions accuracy

Every pre-kickoff prediction is logged to SQLite with the match, market, model probability, and bookmaker odds at time of logging. Settled after results come in. Track record is visible on the [Predictions](https://wc26.tinjak.com/predictions) page once games are played.
