# Model multis — improvement research

Date: 2026-06-24
Author: research pass on /picks/model-multis (LiveHub "Model picks" card)
Scope: why the model only publishes 2-leg multis, what research says about
optimal leg count + missing filters, and a concrete change list with the
risk-ranked order to ship them.

---

## TL;DR

Three things are true at once and they explain everything the user is seeing:

1. The generator is **structurally hardcoded to 2 legs**. It is not "deciding
   the data only supports 2" — it never even considers a 3-leg shape.
2. Even if we unblocked it, the published-probability gate (12% floor) would
   filter out almost every 3+ leg shape unless every leg is a heavy
   favourite, because three 60% legs only land 22% of the time.
3. We are missing four filters the literature treats as table stakes for
   accumulator construction: **independence between legs, kickoff
   diversification, CLV-positive market preference, and compounded-margin
   awareness**. Without these, the same model edge gets eaten by hidden
   correlation and overround as we add legs.

Recommendation: keep singles + 2-leg as the default, but **let the model
publish 3 or 4 legs *only when the marginal leg has its own +5% edge AND the
compounded margin stays under 20%***. That's the "if it's confident, let it
do more" rule the user asked for, expressed in money terms instead of vibes.

Estimated work: ~3-4 hours of focused engineering for the leg-count
extension + the four missing filters. No new data sources needed.

---

## Where the "only 2 legs" comes from

File: `backend/api/routes/model_picks.py`

Two generators, both fixed at 2:

- **SGM_PAIRS** (line 56) is a `list[tuple[str, str]]` — every entry is a
  pair of market keys. There is no SGM_TRIPLES, and the loop in
  `_candidates_from_match` iterates `for a, b in SGM_PAIRS`. A 3-leg
  same-match multi like home_win + over_2_5 + btts can never be considered,
  even when the score grid says all three are simultaneously +EV.
- **_cross_match_candidates** (line 273) takes the single best leg per
  match and runs `for i, leg_a in enumerate(best_legs): for leg_b in
  best_legs[i+1:]`. Strict pairs. No triple loop, no `combinations(legs,
  3)`.

The downstream gates (`MIN_COMBINED = 0.12`, `MIN_EDGE_OVER_BOOK = 0.05`,
`MIN_PER_LEG_EDGE = 0.03`) would also push back on 3-leg shapes, but they
never get the chance to.

For comparison: `/betting/acca` (the user-facing builder at /acca?tab=model)
**does** support k=2..5 and uses `itertools.combinations`. So the codebase
already knows how to do this — it's only the curated-picks generator that
was deliberately scoped to doubles.

---

## What the research says about optimal leg count

Synthesised from four sources (full extracts at end of doc):

| Source | Recommended leg range | Reasoning |
|---|---|---|
| Rowdie (margin compounding study) | Singles only | 5% per leg → 22.6% compounded margin on a 5-fold |
| SportsBoom (Bruce Douglas guide) | 4-5 max | 6% margin × 5 = 33.8% compounded; "rarely add more than four legs" |
| Bet With Steve (singles vs accas) | Singles primary, accas for promo-boosted shapes | Acca insurance + odds boost can offset compounding |
| Non-League FP (parlay construction) | "Match leg count to the quality of analysis" | Don't pad — better a 2-leg with two believable edges than a 4-leg with two fillers |

### Combined-probability reality (60% per leg)

| Legs | Combined prob | Compounded margin (5% per leg) |
|---|---|---|
| 1 | 60% | 5% |
| 2 | 36% | 9.75% |
| 3 | 21.6% | 14.26% |
| 4 | 13.0% | 18.55% |
| 5 | 7.8% | 22.62% |

Two operational consequences:

1. **The 12% combined floor we currently enforce is structurally a
   3-leg-maximum gate at sensible per-leg probabilities.** Three 60% legs
   = 21.6% (passes); four 60% legs = 13.0% (just passes); five 60% legs
   = 7.8% (rejected). So if we want 4 or 5 legs we need to drop the floor
   *or* require higher per-leg probabilities.
2. **The compounded margin is the silent killer.** A 5% per-leg edge
   becomes a ~15% disadvantage by the 5th leg unless every leg also has
   true +EV. This is exactly why the per-leg-edge filter (currently 3%) is
   the most important one to tighten — not loosen — as legs grow.

### The "confidence → more legs" rule, formalised

The user's instinct ("if it's confident, let it do more") is correct, but
"confidence" should mean *every marginal leg still has positive expected
value after the bookmaker margin is fully accounted for*. Concretely:

```
allow N legs IF:
  - every leg has a per-leg edge >= MIN_PER_LEG_EDGE_AT_N
  - compounded margin (∏ per_leg_overround) <= 0.20   # 20% cap
  - combined model prob >= MIN_COMBINED_AT_N
  - combined EV vs best book >= MIN_EDGE_OVER_BOOK
```

Where the per-leg edge floor *rises* with N (more legs = each must do more
work to overcome compounded vig):

| N legs | Min per-leg edge | Min combined prob |
|---|---|---|
| 2 | 3% (current) | 12% (current) |
| 3 | 5% | 10% |
| 4 | 7% | 7% |
| 5+ | 10% | 5% (rare) |

This is conservative on purpose. A 5-fold needs each leg to be a 10%-edge
true monster — we should almost never have one. Two or three legs will
remain the default outcome of the algorithm, but a rare 4-fold
high-confidence pick can now actually publish.

---

## Filters / data we are missing

These are research-blessed but absent from `model_picks.py`:

### 1. Independence between cross-match legs (HIGH IMPACT)

> "Two selections from same league depending on same form trend or weather
> conditions create correlation risk. Independence between legs is a
> structural quality of a well-built accumulator." — Non-League Football
> Paper

Current code: only the same-match dedupe (rejects two SGMs from the same
match). Two cross-match legs in the same WC group, or both away teams
travelling on the same weather front, are treated as independent.

**Fix**: in `_cross_match_candidates`, for any candidate combo:

- Reject if 2+ legs from the same group (group-stage results are
  correlated — Team A's group-mate result changes Team B's tactical
  approach in the final round of group matches).
- Reject if 2+ legs from the same kickoff window (±30 min) when the legs
  bet on similar markets (e.g. two Over 2.5s same time = same weather
  front, same global news shock risk).
- Reject if 2+ legs benefit the same team (we already do this in
  `/betting/acca` lines 234-249 — port the same logic here).

### 2. Compounded-margin awareness (HIGH IMPACT)

We never compute or surface the compounded margin. Adding it:

```python
per_leg_overround = sum(1/o for o in book_prices) - 1.0   # at the market level
compounded = product(1 + overround_per_leg) - 1
```

If `compounded > 0.20`, reject the multi regardless of model EV — this
short-circuits the "model EV looks good but the bookie has already eaten
the edge" failure mode.

### 3. Kickoff diversification + payout staging (MEDIUM IMPACT)

> "Use a trusted spread betting strategy to make calculated picks on the
> common -110 lines. Avoid blindly stacking favorites… Weather is a silent
> killer in NFL parlays." — next.io parlay strategy guide

For WC2026 specifically: don't stack 3 group-stage matches that all kick
off in the same Mexican afternoon humidity slot. Two is fine; three is a
correlation risk (heat, scheduling fatigue at the venue cluster).

### 4. CLV-positive market preference (MEDIUM IMPACT)

We already compute CLV in `backend/betting/market.py:closing_line_value`
and log it on settled picks. We don't currently bias multi construction
toward markets where our historical CLV is positive.

Add a per-market CLV table (last 30 settled picks per market, mean CLV);
in `_cross_match_candidates`, prefer legs whose market has mean CLV > 0
when scoring. Cheap, uses data we already have, statistically the single
strongest signal that "this market is genuinely +EV for us".

### 5. Steam against the pick (LOW IMPACT, FAST WIN)

We compute `get_steam_signal` in `/betting/value` but ignore it in the
model-multi generator. If sharp money has moved the line AGAINST our pick
in the last few hours, sharp action thinks we're wrong; we should skip
the leg. Already plumbed, just unused here.

### 6. Bookmaker payout cap awareness (LOW IMPACT, USER-FACING)

> "Many bookmakers… have small max payout limits… A £180,000 acca that
> caps at £100,000." — Bet With Steve

When we publish a multi with combined_book_odds > 100 (i.e. a £10 stake
would pay £1,000), surface a small warning in the UI: "Cap your stake;
many AU books cap multi payouts at A$250k". Doesn't affect the math but
prevents user mis-stakes.

### 7. Acca boost / insurance offer awareness (LOW IMPACT, OUT OF SCOPE)

Research consistently flags that 4-fold acca boost promotions (5-10%)
mathematically change which leg count is optimal. We don't track which
AU books are currently offering acca boost during the WC, and that data
isn't worth pulling for this site. Note it and move on.

---

## Concrete change list (ranked by effort × impact)

### Priority 1 — unblock leg count

In `backend/api/routes/model_picks.py`:

- Replace `SGM_PAIRS: list[tuple[str, str]]` with `SGM_SHAPES:
  list[tuple[str, ...]]` — keep all current pairs, add the high-correlation
  triples that the score grid actually has an edge on:
  - `("home_win", "over_2_5", "btts")` — classic favourite goalfest
  - `("away_win", "over_2_5", "btts")` — classic upset goalfest
  - `("draw", "under_2_5", "btts_no")` — classic dead-rubber 0-0 / 1-0
- In `_candidates_from_match`, iterate shapes of any length: compute joint
  prob off the grid using the union of all leg masks (the existing
  `joint_probability_from_grid` already accepts a list of any length).
- In `_cross_match_candidates`, replace the nested-pair loop with
  `combinations(best_legs, k)` for k in 2..MAX_LEGS, with the per-N
  thresholds from the "confidence → more legs" table above.
- Add a `MAX_LEGS = 4` constant. Five legs requires almost certainly
  unreachable per-leg edge thresholds — leave it as a hard cap.

### Priority 2 — add the four filters

In the same file:

- **Compounded-margin gate**: compute per the formula above; reject if
  > 20%. Single line, single rejection branch.
- **Group/kickoff/team beneficiary dedupe** in `_cross_match_candidates`:
  reuse the team-beneficiary logic from
  `backend/api/routes/betting.py:234-249`; add a kickoff-window check
  using the `Match.kickoff` we already have; add a group check using
  `Match.group`.
- **CLV bias on scoring**: add a small `clv_boost` to the existing score
  formula: `score = combined_prob * ln(1 + edge) * (1 + 0.1 * mean_market_clv)`.
  Mean is over the last 30 settled picks for that market key — query
  `PredictionSnapshot` or whatever pick-history table holds CLV (need to
  verify the exact column name when implementing).
- **Steam-against rejection**: in both candidate builders, after
  resolving the leg price, call `get_steam_signal(match_id, market,
  model_prob)`; if the signal is "moving against us", skip the leg.

### Priority 3 — user-facing surfacing

Frontend `frontend/app/...` (LiveHub model-picks card):

- Show compounded margin next to combined odds.
- Tag each card with leg count + label:
  - 2 legs → "Tight double"
  - 3 legs → "Balanced treble"
  - 4 legs → "Bold 4-fold" (rare, only when confidence cleared all four leg gates)
- If combined_book_odds > 100, show the payout-cap warning line.

### Priority 4 (defer) — what NOT to ship now

- 5-leg multis. The per-leg edge floor that would make them honest is
  almost never reachable on a WC slate. Leave the constant at MAX_LEGS=4.
- Acca boost / promo integration. No clean data source, not worth the
  scraping effort.
- Per-leg model standard-error compounding. The point-estimate variance
  ignores leg-leg covariance entirely; doing this right is a research
  project, not a sprint task. Note it as a known limitation in the UI
  ("model assumes leg independence outside SGMs").

---

## Open questions for the user

1. **Aggressiveness preference**: the per-N edge floors above are
   conservative (4-fold needs every leg to be 7% +EV). Do you want the
   model to publish 3-4 leg multis often (loosen to 5% / 5% / 5%) or rarely
   (keep at 5% / 7% / 10%)? Default proposal is the conservative table.
2. **Group-stage correlation**: in the final round of WC group matches,
   two matches in the same group kick off simultaneously and outcomes are
   genuinely correlated (a team that knows it's qualified plays
   differently). Do we want to *forbid* multis touching both final-round
   matches in the same group, or just warn? Default proposal: forbid.
3. **Promotion of confidence visually**: do you want a single "best multi"
   highlighted on the card (current pattern is multiple cards equal
   weight), or rank-sorted with the top one badged?

---

## Source quotes (for the record)

**Rowdie — margin compounding table**

> "If each leg has a margin of 5%, then with every additional selection,
> the margin compounds, making it increasingly difficult to achieve a
> profitable outcome." — 2 legs: 9.75% / 3 legs: 14.26% / 4 legs: 18.55%
> / 5 legs: 22.62%

**SportsBoom — Bruce Douglas, accumulator strategy guide**

> "Stick to: 1x2, over/under goals, Asian handicaps. Rarely add more
> than four legs… 4-fold at 70% per leg = ~24% win chance; 10-fold at
> 70% per leg = ~2.8% win chance."

**Bet With Steve — singles vs accumulators**

> "Don't add legs just to push odds up — each extra selection dramatically
> reduces chances. Padding with unnecessary picks is usually what kills it."

**Non-League FP — parlay construction**

> "Independence between legs is a structural quality of a well-built
> accumulator. The optimal number of legs for today's accumulator is
> determined by how many selections genuinely meet the analytical
> standard, not by a target for the combination."

---

## Appendix — live state (snapshot 2026-06-24)

Pulled from prod `/api/proxy/model-multis`:

- 3 active multis published right now.
- All 3 are 2-leg (sgm + sgm + cross).
- Combined odds range 3.18 to 10.44; EV% range +24% to +77% (the +77% is a
  red flag the existing guardrails should be reviewing — flagging for
  follow-up).
- Zero 3-leg, zero 4-leg, zero 5-leg multis exist in the system because
  the generator has never had the capacity to create one.
