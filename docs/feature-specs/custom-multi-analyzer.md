# Feature spec: Custom multi analyzer ("run my own slip through the model")

Status: NOT BUILT. Spec for a future build (Hermes agent + DeepSeek). Read the guardrails before writing code.

## What and why

Today the value board and the acca builder only show the model's OWN pre-built combos. A user
who has built (or is about to build) their own multi at a bookmaker has no way to ask "what does
the model think of THIS slip?". This feature lets them assemble any set of legs and get an
instant, honest, model-backed verdict, the same analysis we currently do by hand.

Real use case that motivated this (use it as the worked example / acceptance test):
> Slip: Portugal v DR Congo Over 1.5, England v Croatia Under 2.5, Colombia v Uzbekistan
> Over 2.5, Ghana v Panama both teams to score. bet365 prices the multi at 8.24.

The model's answer for that slip (these are the numbers the feature must reproduce):
- per-leg model probabilities: 74%, 58%, 54%, 52%
- combined model probability (all four are different matches, so independent): 0.74 x 0.58 x 0.54 x 0.52 = 0.1205 (12.05%)
- model fair multi odds = 1 / 0.1205 = ~8.30
- EV at the book's 8.24 = 0.1205 x 8.24 - 1 = -0.7% (a hair under fair, no edge)
- verdict: priced about right, NOT value, and three of four legs are the model AGREEING with the
  bookie (no edge), so the slip tracks the book rather than the model.

## What it must do

1. Let the user add legs: pick a match, pick a market/outcome. Markets come from the existing
   per-match market sheet (`GET /matches/{id}/markets`), which already returns the model's
   probability for every market we price (1X2, double chance, over/under at each line, BTTS, team
   totals, clean sheet, Asian handicap, exact score, half-time).
2. Compute the combined MODEL probability of the slip:
   - Legs in DIFFERENT matches are independent: multiply their probabilities.
   - Legs in the SAME match are CORRELATED and MUST NOT be multiplied. Use the exact joint from
     the score grid via `backend/betting/sgm.py:joint_probability_from_grid(matrix, markets)`,
     which already exists and is tested. Build the match grid from the prediction lambdas
     (`build_score_matrix(lambda_home, lambda_away, rho=-0.13)`). This is the whole point: a
     favourite winning lifts Over but suppresses BTTS, and multiplying same-match legs is wrong.
   - So: group legs by match, take the grid-joint within each match, then multiply across matches.
3. Show: combined model probability, model fair odds (1/prob), and let the user enter the price
   their bookmaker offers for the multi. Compute EV = model_prob x book_price - 1. Take it only if
   the book price is ABOVE the fair odds.
4. Per-leg edge attribution (the most useful part, and the anti-bookie-follower point): for each
   leg, show whether the model has an EDGE (model probability clearly above the leg's market-implied
   probability) or NO EDGE (model agrees with the book). A multi made of no-edge legs just compounds
   the bookmaker margin. Flag that plainly ("3 of 4 legs are no-edge, this tracks the book not the
   model").
5. Reuse the calibration-shrunk staking and the bankroll outcome / risk-of-ruin view already in
   `frontend/components/value/ValueList.tsx` so the user sees a suggested stake and the variance.

## Where the pieces already are

- Per-match model market probabilities: `GET /matches/{id}/markets` (route in
  `backend/api/routes/predictions.py` / `betting.py`; builder in `backend/betting/markets.py`).
- Same-match correlated joint: `backend/betting/sgm.py:joint_probability_from_grid` (exact, tested
  in `backend/tests/test_sgm_grid.py`). The SGM route `POST /betting/sgm` already does single-match
  correlated multis; this feature generalises it to multi-match slips.
- Score grid: `backend/models/poisson.py:build_score_matrix`; lambdas come from the prediction.
- EV / Kelly: `backend/betting/ev.py`, `backend/betting/kelly.py` (quarter_kelly, multi_kelly).
- Market-implied (for edge attribution) and Shin de-vig: `backend/betting/market.py`.
- Acca page + value cards (UI patterns to match): `frontend/app/acca/page.tsx`,
  `frontend/components/value/ValueList.tsx` (bankroll box, BankrollOutcome sim, stake helper).

Suggested shape: a new `POST /betting/analyze-multi` taking `[{match_id, market}]` + optional
`book_price`, returning per-leg model prob + edge flag, combined prob (correlation-correct), fair
odds, and EV. A "Build your own" tab/panel on `/acca` that posts to it.

## GUARDRAILS (hard rules, do not violate)

- **Correlation is mandatory.** Same-match legs MUST go through `joint_probability_from_grid`, never
  a naive product. Cross-match legs multiply. Getting this wrong silently mis-prices every slip.
- **Model-first, never a bookie-follower.** The product's whole value is the INDEPENDENT model
  finding where it DISAGREES with the book, and grading itself against the close. Do not add "follow
  the line movement / steam" signals. Edge attribution should highlight model-vs-market disagreement,
  not tell users to mirror the book.
- **Calculated, not guessed; validate before shipping.** Reproduce the worked example above exactly
  as a test. Any model/EV change must be checked, not asserted. Add tests alongside
  `test_sgm_grid.py`.
- **Stop-slop copy.** No em-dashes anywhere in user-facing text. No AI-slop words (delve, seamless,
  unleash, elevate, game-changer). Plain, active voice. Match the existing honest tone.
- **Responsible gambling.** Keep the framing: fair odds are a model estimate not a guarantee, a
  multi loses most of the time, stake small (calibration-shrunk quarter-Kelly), 18+ footer stays.
- **Stack + style.** Next.js 14 App Router, FastAPI, SQLite, hand-rolled SVG (NO chart library),
  dark + emerald tokens (`surface-*`, `edge`, emerald accent; amber not red for the negative side,
  colour-blind-safe). TypeScript must pass `tsc --noEmit`; the frontend must `next build` clean.
- **Never lose data.** `data/wc2026.db` (the prediction ledger) is gitignored and VPS-only. Back it
  up before any deploy (`scripts/backup-db.sh`, or the documented `sudo cp` line). Never commit
  secrets or `backend/.env`.
- **Deploy procedure** is in `docs/OPERATIONS.md` (`scripts/deploy.sh`: backup, ff-only pull, build
  stamped with the commit, recreate). On the `/mnt/c` working tree, watch the CRLF churn trap
  (`git diff --ignore-cr-at-eol` should be empty for non-real changes); `core.autocrlf` is false.
- **Quota.** The Odds API is one free key, ~500 credits/month, captured to the persisted odds cache.
  This feature reads the MODEL's market sheet and existing cached odds; it must not add per-request
  odds-API calls.

## Acceptance test

Feed the worked-example slip and assert: per-leg probs 74/58/54/52 (within rounding), combined
~12.0%, fair odds ~8.3, EV at 8.24 ~ -0.7%, and the per-leg edge flags mark Portugal Over 1.5 and
Ghana BTTS as no-edge. Add a same-match case (e.g. a team win + Over in one match) and assert the
joint is NOT the product of the two marginals.
