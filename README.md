<div align="center">
  <img src="docs/logo.svg" width="64" alt="WC26 Predictor logo" />
  <h1>WC2026 Predictor</h1>
  <p>Data-driven predictions for every 2026 FIFA World Cup match, free to use.</p>
  <a href="https://wc26.tinjak.com"><strong>▶ Try it live at wc26.tinjak.com</strong></a>
  &nbsp;&nbsp;
  <img alt="93 tests passing" src="https://img.shields.io/badge/tests-93%20passing-22c55e?style=flat-square" />
  <img alt="Python 3.12" src="https://img.shields.io/badge/python-3.12-3b82f6?style=flat-square" />
  <img alt="Next.js 14" src="https://img.shields.io/badge/next.js-14-ffffff?style=flat-square" />
</div>

---

## What is this?

A free website that predicts 2026 World Cup matches. A statistical model reads six years of international results, current squad strength, and live bookmaker odds, then estimates the chance of every outcome: who wins, how many goals, who reaches the knockouts, who lifts the trophy.

You do not need to understand the maths to use it. Open a match, read the percentages, and check the **fair odds** against whatever price your bookmaker is offering. If their price is bigger than ours, the model thinks you have an edge.

Everything updates as results come in, and the model grades its own accuracy in public so you can judge it for yourself.

**[Open the live site →](https://wc26.tinjak.com)**

---

## See it in action

| Who wins the World Cup? | The model's report card |
|---|---|
| [![Tournament projections](docs/screenshots/winner.png)](https://wc26.tinjak.com/winner) | [![Model report card](docs/screenshots/performance.png)](https://wc26.tinjak.com/performance) |
| Title, knockout and group-winner odds from 20,000 tournament simulations. | Live accuracy, scored with the same rules a forecasting researcher uses. |

| Match detail + fair odds on 30 markets | Value board with best-price line-shopping |
|---|---|
| [![Match detail](docs/screenshots/match-detail.png)](https://wc26.tinjak.com/match/M001) | [![Value board](docs/screenshots/value-board-new.png)](https://wc26.tinjak.com/value) |
| Every market priced from one model, so you can shop your own bookmaker. | The best price across books, who has it, plus any cross-book sure-bets. |

| Per-team pages for all 48 nations | |
|---|---|
| [![Team page](docs/screenshots/team-detail.png)](https://wc26.tinjak.com/team/ar) | Each team's full path: win the group, reach each round, win the trophy, with fixtures and squad. |

---

## What you can do with it

**Read any match.** Win, draw and loss percentages for all 72 group games, plus a plain-English "why" behind each one.

**See who wins the cup.** A 20,000-run simulation of the whole tournament, including the real knockout bracket, gives each nation its chance to top its group, reach the last 32, and win it all.

**Find value on 30+ markets.** Not just the winner. The match page prices double chance, both teams to score, clean sheets, team totals, exact score, Asian handicaps, half-time/full-time and more, each with the model's fair odds. The value board shows the best price across bookmakers and which one has it, so you always take the longest price.

**Track the model honestly.** Every pick is locked in before kickoff and scored after the result. The report card shows how sharp the model has been, and how it improves with each change.

---

## New to this? How to read a prediction

**Percentages are chances.** "France 62%" means the model gives France a 62% chance to win that match. Over many matches, calls like that should come true about 62% of the time. The report card checks whether they do.

**Fair odds is the break-even price.** Next to each market you will see a number like `1.45`. That is the lowest decimal price worth taking. If your bookmaker offers **more** than the fair odds (say `1.70`), the model says that bet has value. If they offer less, skip it.

**Shop around.** The same bet is priced differently across bookmakers. The fair-odds sheet lets you compare any book's price to the model's, on any market, not just the headline ones.

**One number tells you most.** On the report card, **Closing Line Value (CLV)** compares the price you took against the sharp price just before kickoff. Beating the close, over time, is the clearest sign an edge is real, well before a win-rate can prove it.

> Bet for fun, with money you can afford to lose. A model is an estimate, not a guarantee. If gambling stops being fun, take a break.

---

## How the model works

For the curious. The short version: a goal model trained on recent results, corrected so it compares teams across confederations fairly, nudged by match context, then sanity-checked against the betting market.

### The problem with the naive approach

Most public predictors use raw ELO or a basic Poisson model. Both break on cross-confederation games. An ELO of 1750 in Africa is not the same as 1750 in Europe: Algeria built its rating shutting out weaker neighbours, so running that number straight against Argentina once gave Algeria a 33% chance to win. Nonsense. The whole design fixes that class of error.

### Layer 1: Dixon-Coles goal model

A [Dixon-Coles](http://www.math.su.se/matstat/reports/seriea/2000/rep2/report.pdf) model fits ~6 years of international results, weighting recent matches more (time-decay `ξ = 0.0018/day`, tuned by backtest). Each team gets an attack and a defence rating. Dixon-Coles adds a low-score correction that fixes the way plain Poisson under-counts 0-0 and 1-1 draws.

### Layer 2: Confederation-aware ELO blend

Dixon-Coles ratings are accurate within a confederation but distort across them, so the model blends them with [eloratings.net](https://www.eloratings.net) ELO, which already encodes real World Cup results:

```
Cross-confederation:  45% Dixon-Coles + 55% ELO
Same-confederation:   55% Dixon-Coles + 45% ELO
```

Confederation strength offsets (UEFA, CONMEBOL, AFC, CONCACAF, CAF, OFC) anchor the comparison. The fix turned a broken "Brazil 37% / Morocco 38%" into "Brazil 58% / Morocco 20%", which lines up with the bookmakers.

### Layer 3: Nine context modifiers

Rest days, dead-rubber risk, squad market value, injuries, head-to-head, weather, travel, confirmed lineups, and set-piece strength each nudge the expected goals. They combine in log space under a single ±0.25 cap, so correlated factors can never compound into an extreme the model was not built for. Altitude (Mexico City, Guadalajara) adds goals on top, since both teams score more in thin air.

### From goals to every market

The adjusted goal expectations feed one 9×9 score-line grid. Win/draw/loss, over/under at every line, both teams to score, team totals, clean sheets, Asian handicaps, exact scores and half-time markets all come from that single grid, so the whole sheet stays consistent. The tournament simulation samples scorelines from the same grid, then runs the official bracket 20,000 times.

### Betting maths

Expected value compares the model's probability to the bookmaker price. The market is de-vigged with **Shin's method**, which corrects the favourite-longshot bias better than simple normalisation, and the model is blended 70/30 with that fair line. Stakes use **quarter-Kelly**, capped at 5% of bankroll, because Kelly punishes an over-estimated edge hard.

### Why the model is left alone right now

Over the first ~14 World Cup matches the live calibration looks shaky. That is a small sample. A neutral-venue backtest on 304 out-of-sample matches, the condition that actually matches an all-neutral tournament, shows the model well-calibrated (calibration error 0.065, best-fit temperature 0.8). Re-tuning to 14 games would overfit against 300 that say it is fine, so the probabilities stand.

---

## Validation

The goal model is gated by a walk-forward backtest (`backend/eval/backtest.py`) that replays ~1,500 out-of-sample internationals, refitting Dixon-Coles at each cutoff and scoring **RPS, log-loss, Brier and calibration** against an ELO and a climatology baseline. Run it with `python -m backend.eval.backtest`.

What it has settled so far:

- Time-decay `ξ` dropped from 0.00325 to **0.0018/day**. The club-tuned value decayed sparse international data ~3× too fast.
- The Dixon-Coles / ELO blend optimum is a flat 40-60% Dixon-Coles, so the model leans on ELO more than it used to.
- The model is already well-calibrated (calibration error ≈ 0.03, optimal temperature ≈ 1.0), so no post-hoc fudge was added.

Live predictions are scored the same way. Every upcoming match's full distribution is snapshotted before kickoff, and `/history/calibration` reports RPS, Brier and reliability over finished matches, unbiased by which bets the value board chose.

---

## Stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 14 (App Router) |
| Backend | FastAPI + APScheduler |
| Database | SQLite via SQLAlchemy |
| Odds | The Odds API (Bet365, Sportsbet, Unibet) |
| ELO | eloratings.net (24h cache) |
| Form | martj42/international_results (6h cache) |
| Deployment | Docker Compose behind Nginx Proxy Manager |
| Tests | pytest (93 tests) + a walk-forward backtest |

---

## Run your own instance

You need Docker and, for live odds, free API keys from [The Odds API](https://the-odds-api.com) and [API-Football](https://www.api-football.com). Predictions and the tournament simulation run without any keys.

```bash
git clone https://github.com/jasoisjaso/worldcup26.git
cd worldcup26

cat > backend/.env <<EOF
THE_ODDS_API_KEY=your_odds_api_key_here
API_FOOTBALL_KEY=your_api_football_key_here
EOF

docker compose up --build -d
```

Frontend: `http://localhost:3000`. API docs: `http://localhost:8000/docs`.

### Tests

```bash
# in the repo root
python -m pytest backend/tests/ -v
python -m backend.eval.backtest          # walk-forward backtest of the goal model
```

---

## Accuracy, in public

Every pre-kickoff pick is logged with the match, market, model probability and bookmaker price, then settled after the result. The full record lives on the [report card](https://wc26.tinjak.com/performance). No edits, no hindsight.
