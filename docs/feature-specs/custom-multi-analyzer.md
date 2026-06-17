# Feature spec: Custom multi analyzer + optimizer ("build the best bet")

Status: NOT BUILT. Spec for a future build (Hermes agent + DeepSeek). Read the guardrails before
writing code. This is the brief; build to it.

## What and why

Today the value board and the acca builder only show the model's OWN pre-built combos. A user who
wants to build their own multi, test "what if I swap this leg", and find the best bet has no tool.
This feature turns the /acca page into an interactive bet-slip lab: drop in any legs across any
matches, instantly get the model's verdict (correlation-correct combined probability, fair odds, EV
vs the price your bookmaker shows), see it as live graphs, and get nudged toward a genuinely better
bet when one exists.

It came out of a real session of doing this by hand. The user iterated a slip four times; each
iteration is a worked example below and a required acceptance test.

## What it must do

1. **Assemble any legs.** Pick a match, pick a market/outcome. Markets come from the existing
   per-match sheet (`GET /matches/{id}/markets`), which already returns the model probability for
   every market we price.
2. **Price the slip correctly (correlation is the whole point).**
   - Legs in DIFFERENT matches are independent: multiply probabilities.
   - Two or more legs in the SAME match are CORRELATED and MUST NOT be multiplied. Compute the exact
     joint off the score grid with `backend/betting/sgm.py:joint_probability_from_grid(matrix, keys)`
     (already built and tested). Build the grid from the prediction lambdas:
     `build_score_matrix(lambda_home, lambda_away, rho=-0.13)`. Group legs by match, take the
     grid-joint within each match, then multiply across matches. Always show the user the
     same-match joint vs the naive product so the correlation is visible (sometimes it is large,
     sometimes ~0; both are informative).
3. **Verdict.** Combined model probability, model fair odds (1/prob), user enters the bookmaker's
   price for the slip, EV = model_prob x price - 1. Value only when price > fair odds.
4. **Per-leg edge attribution.** For each leg flag EDGE (model probability clearly above the leg's
   market-implied probability) vs NO-EDGE (model agrees with the book). A multi of no-edge legs just
   compounds the bookmaker margin. State it plainly.
5. **The optimizer / "nudge me to a better bet" (the feature the user most wants).** Given the
   current slip and an objective the user picks (maximize EV, or maximize chance of landing), search
   single-leg changes and surface the best one, with the reason and the before/after numbers:
   - swap a leg's market within the same match (e.g. the session's "BTTS 52% -> Over 1.5 72%" lifted
     win chance; "Under 2.5 -> Draw / Croatia-or-draw" lifted EV from -0.7% to +34.7%),
   - drop the weakest leg (fewer legs = higher hit rate, lower payout; always offer this),
   - point to the single best value bet on the slate if the slip has no edge.
   Honesty rule: nudge toward VALUE (model edge) and toward the user's chosen objective, never toward
   longshots-for-payout or toward following the book. If the slip is already the model's best
   expression, say so rather than inventing a change.
6. **Live graphs as the slip is built** (hand-rolled SVG, no chart library, dark + emerald):
   - the bankroll outcome / risk-of-ruin distribution of the slip (reuse `BankrollOutcome` /
     `simulateSlate` in `frontend/components/value/ValueList.tsx`),
   - combined win probability and fair-vs-offered odds, updating as legs change,
   - a per-leg edge bar (model% vs market% per leg),
   - how each leg moves the combined probability (so the user sees the cost of every extra leg).

## Markets to support

From the grid (exact, already priced): 1X2, double chance (1X / X2 / 12), over/under at every line,
**goal bands** (e.g. "2-4 goals" = over_1_5 AND under_4_5; express bands as the intersection of an
over and an under, which `joint_probability_from_grid` already handles), BTTS yes/no, team totals,
clean sheets, Asian handicaps, exact score, half-time markets. All of these are pure functions of the
final score, so they price exactly and correlate correctly within a match.

## Cards and corners (the user asked; be honest here, it is a stretch)

The model already produces `expected_corners` and `expected_cards` per match (see
`backend/api/routes/predictions.py` / the prediction object). To offer corner/card MARKETS
(over/under corners, over/under cards), add a thin Poisson layer on those expected values in
`backend/betting/`. BUT:
- These are NOT validated. We have no calibration or settled-result history for corners/cards, and
  the expected values lean on assumptions, not a fitted model. So mark any corner/card market as
  LOWER CONFIDENCE in the UI, exclude them from the edge-attribution "value" flag (we cannot claim an
  edge we have not validated), and never let the optimizer nudge a user toward them as "value".
- Do not fake precision. A Poisson on a hand-set expected corner count is a guess dressed as a
  market. Ship it as "indicative only" or leave it out until there is a validated corners/cards
  model. Same goes for any other market we do not price from the validated goal grid.

## Worked examples (use as acceptance tests; numbers are from the live model)

All four are the same base slip with the England-Croatia leg changed. Base legs: Portugal-DR Congo
Over 1.5 (model 74%), Colombia-Uzbekistan Over 2.5 (54%), Ghana-Panama Over 1.5 (72%). England-Croatia
lambdas: home(England) 1.221, away(Croatia) 1.138.

| England-Croatia leg | Eng-Cro model prob | Slip combined | Fair odds | Book price | EV |
|---|---|---|---|---|---|
| Under 2.5 | 58% | 16.7% | 5.99 | 5.95 | -0.7% |
| Under 2.5 + Ghana BTTS instead of Ghana Over 1.5 | 58% | 12.05% | 8.30 | 8.24 | -0.7% |
| Draw | 32% | 9.2% | 10.86 | 12.75 | +17.4% |
| Croatia-or-draw (X2) AND 2-4 goals | 38.8% (joint; ~= 0.636 x 0.609 product) | 11.2% | 8.96 | 12.06 | +34.7% |

The optimizer must be able to get from the first row (-0.7%, no edge) to the last (+34.7%) by
changing only the England-Croatia leg, because that match is the only one the model disagrees with
the book on. Assert the same-match X2 + 2-4-goals joint is computed from the grid (here it happens to
~equal the product; include a case where it does NOT, e.g. a heavy favourite's win + Over, to prove
the correlation path is exercised).

## Where the pieces already are

- Per-match model market probs: `GET /matches/{id}/markets` (builder `backend/betting/markets.py`).
- Same-match correlated joint: `backend/betting/sgm.py:joint_probability_from_grid` (tested in
  `backend/tests/test_sgm_grid.py`); `POST /betting/sgm` already does single-match versions.
- Score grid: `backend/models/poisson.py:build_score_matrix`; lambdas from the prediction.
- Market-implied + Shin de-vig (edge attribution): `backend/betting/market.py`.
- EV / Kelly: `backend/betting/ev.py`, `backend/betting/kelly.py` (quarter_kelly, multi_kelly).
- Outcome sim + stake helper + bankroll box: `frontend/components/value/ValueList.tsx`
  (`simulateSlate`, `BankrollOutcome`, `pickStake`), value cards, acca page `frontend/app/acca/page.tsx`.
- Corners/cards expected values: the prediction object (`expected_corners`, `expected_cards`).

Suggested shape: `POST /betting/analyze-multi` taking `[{match_id, market}]` + optional `book_price`,
returning per-leg model prob + edge flag, the same-match joint vs product, combined prob, fair odds,
EV, and the optimizer's top suggested change. A "Build your own" tab on `/acca` that posts to it and
renders the live graphs.

## GUARDRAILS (hard rules, do not violate)

- **Correlation is mandatory.** Same-match legs MUST go through `joint_probability_from_grid`, never
  a naive product. Cross-match legs multiply. Getting this wrong silently mis-prices every slip.
- **Model-first, never a bookie-follower.** The product's value is the INDEPENDENT model finding where
  it DISAGREES with the book, and grading itself against the close. No "follow the steam / line
  movement" signals. The optimizer nudges toward the model's edge and the user's objective, never
  toward mirroring the book or toward longshots just to fatten the price.
- **Do not invent edges we have not validated.** Cards/corners (and anything not priced from the
  validated goal grid) are lower-confidence, excluded from value claims, and never nudged as value.
  Calculated, not guessed.
- **Validate before shipping.** Reproduce all four worked examples exactly as tests, plus a same-match
  correlation case where the joint differs from the product. Add tests beside `test_sgm_grid.py`.
- **Stop-slop copy.** No em-dashes in user-facing text. No AI-slop words (delve, seamless, unleash,
  elevate, game-changer). Plain, active voice. Match the existing honest tone.
- **Responsible gambling, kept honest.** Fair odds are a model estimate not a guarantee; a multi loses
  most of the time (show the hit rate plainly); stake small (calibration-shrunk quarter-Kelly); 18+
  footer stays. Do not cheerlead a bet.
- **Stack + style.** Next.js 14 App Router, FastAPI, SQLite, hand-rolled SVG (NO chart library), dark +
  emerald tokens (`surface-*`, `edge`, emerald accent; amber not red for the negative side, colour-
  blind-safe). `tsc --noEmit` must pass; the frontend must `next build` clean.
- **Never lose data.** `data/wc2026.db` (the prediction ledger) is gitignored and VPS-only. Back it up
  before any deploy (`scripts/backup-db.sh` or the documented `sudo cp`). Never commit secrets or
  `backend/.env`.
- **Deploy** via `docs/OPERATIONS.md` (`scripts/deploy.sh`). On the `/mnt/c` tree watch the CRLF churn
  trap (`git diff --ignore-cr-at-eol` empty for non-real changes; `core.autocrlf` is false).
- **Quota.** One free Odds API key, ~500 credits/month. This feature reads the model's market sheet and
  existing cached odds; it must not add per-request odds-API calls.

## Build order suggestion

1. `POST /betting/analyze-multi` (pricing + correlation + EV + edge attribution) with the four tests.
2. The "Build your own" UI on /acca with live graphs (reuse `simulateSlate`/`BankrollOutcome`).
3. The optimizer / nudge (single-leg search over the user's objective).
4. Cards/corners LAST, behind a "lower confidence, indicative only" label, never as a value claim.
