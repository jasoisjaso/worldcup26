# WC2026 Predictor

Data-driven match predictions for the 2026 FIFA World Cup. Live demo: **[wc26.tinjak.com](https://wc26.tinjak.com)**

---

## What it does

- **Match predictions** — Win/draw/loss probabilities for every group stage match using ELO + Poisson regression
- **Value board** — Compares model probabilities against live bookmaker odds (bet365, Sportsbet, Unibet) to flag positive expected-value markets
- **ACCA builder** — Builds 2-5 leg accumulators from value picks, filtered by matchday
- **Set piece estimates** — Expected corners and cards per match based on published WC research
- **Group standings** — Live table across all 12 groups
- **Prediction tracker** — Every pre-kickoff pick logged automatically; settled after results come in
- **Match 3 watch** — Flags high-stakes final group games where rotation or dead-rubber scenarios apply

---

## Model

**ELO ratings** sourced from live FIFA rankings and updated every 24 hours. Confederation offsets applied and tapered by within-confederation rank — stronger qualifiers receive full offset, weakest qualifiers receive a scaled-down adjustment.

**Venue module** — Host nations (Canada, USA, Mexico) receive crowd advantage bonuses. Mexico City and Guadalajara apply altitude adjustments for unadapted sides. Diaspora cities (Los Angeles, Dallas, Miami) apply soft crowd boosts for Mexico/South American teams.

**Poisson model** — ELO difference converted to expected goal rates (lambda) via log-linear regression. Scoreline matrix built to 9x9. Win/draw/loss, over/under 2.5, both teams score, and Asian handicap probabilities all derived from the same matrix.

**Corner model** — Based on arxiv:2112.13001. `expected_corners = 9.5 + 0.8 * (λ_home + λ_away − 2.6)`, calibrated to WC group stage average of ~9.5 corners.

**Card model** — Tension-weighted: matches between evenly-rated teams produce more cards. `expected_cards = 2.8 + 2.0 * (1 − |P(home_win) − P(away_win)|)`, calibrated to WC 2022 group stage average.

**Odds** — Median of bet365 / Sportsbet / Unibet via The Odds API. EV calculated as `(model_prob × decimal_odds) − 1`. Corner and card markets are model-only — no live odds available.

---

## Stack

| Layer | Tech |
|-------|------|
| Frontend | Next.js 14 (App Router, SSR) |
| Backend | FastAPI + APScheduler |
| Database | SQLite via SQLAlchemy |
| Odds | The Odds API |
| Ratings | FIFA/ELO live feed |
| Deployment | Docker on VPS behind Nginx Proxy Manager |

---

## Running locally

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn backend.api.main:app --reload

# Frontend
cd frontend
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

Set `THE_ODDS_API_KEY` in your environment for live odds.

---

## Screenshots

![Matches page](docs/screenshots/matches.png)
![Value board](docs/screenshots/value-board.png)
![ACCA builder](docs/screenshots/acca.png)
