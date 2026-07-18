# Final weekend bets — bronze final + final (written 2026-07-19 AEST)

Two games left. M103 France v England (bronze), Sun 19 Jul 07:00 AEST.
M104 Spain v Argentina (final), Mon 20 Jul 05:00 AEST.

## Fixes shipped while preparing this

- **M103 kickoff drift**: DB had 19:00 UTC, real kickoff is 21:00 UTC
  (api-football fixture 1591865). The Odds API lists the game at 21:00, and
  `odds.py` matches events within a 60-min kickoff window — so the 2h drift
  meant M103 never attached odds and the value board was blind on it.
  Fixed via `python -m backend.data.sync_kickoffs --apply` on the VPS
  (also corrected M092 by 1h). Board picks for M103 appear on the next
  8h odds refresh / pre-kickoff force refresh.
- **Last pro-tier API day**: queued ~21.5k harvest jobs (player season pages
  1-5 per team-season, transfers, squads, coaches — `scripts/final_day_burn.py`)
  against the idle 74k daily quota before the key drops to free tier.

## Market state (The Odds API, ~14:20 UTC Sat)

M103: France 1.85-1.92 (pin 1.92) / Draw 3.9-4.09 / England 3.8-3.85.
Totals line is **3.25** (pin 1.95/1.95); unibet 3.5 @ 2.12/1.70.
M104: Spain 2.25-2.30 (pin 2.30) / Draw 2.9-3.05 / Argentina 3.6-3.69.
Totals: pin 2.25 @ 2.01/1.88; unibet O/U 2.5 @ 2.25/1.61.

## Model vs market

M103 (lineup-blind model): France 56.9% vs 50.8% devig → +9.4% EV @ 1.92.
Model expects only 2.30 total goals vs market line 3.25. Bronze finals
average 3.80 goals across 20 editions (Opta) — the model has no concept of
dead-rubber openness (knockout-context fix never shipped), so its Under
lean is a KNOWN BLIND SPOT. No totals bet either way in M103.

Team news supports the France lean: Deschamps keeps a near-full attack
(Mbappé, Olise, Doué, Cherki; Saliba + Samba out), England field a B-spine
(Mainoo-Eze pivot, Rogers/Madueke/Rashford) after looking spent in the semi.

M104: model Spain 45.9% vs 42.5% devig → +3.2% EV @ 2.30 (pinnacle).
Over 2.5 model 46.3% vs 41.4% implied → +2.4% EV @ 2.25 (unibet).
Caveat: Elo alone has ARGENTINA 45.9% — the Spain edge comes from
Dixon-Coles tournament form (2-0 over France, 6 clean sheets in 7).
Component disagreement = real uncertainty; stakes stay small.

## The bets (1u = normal single stake)

Singles:
1. Final Over 2.5 @ 2.25 unibet — 0.5u (board core, kelly 0.48%)
2. Final Spain @ 2.30 pinnacle — 0.25u (board core, kelly 0.19%)
3. Bronze France @ 1.92 pinnacle — 0.5u (news-supported, model +9.4%
   but lineup-blind; halve normal Kelly)

Multi (the headline):
4. France (1.92) x Spain (2.30) double @ 4.42 — 0.5u.
   Engine: fair 3.82, land prob 26.2%, EV +15.5%. Both legs independently
   +EV; cross-game so no correlation haircut.
   Alt with same fair value: France x Over 2.5 final @ 4.32 (+14.0%).

Bet-builder (only if priced right):
5. Final SGM Spain & Over 2.5: grid-true fair = 3.73 (legs positively
   correlated, +26% vs naive). Books price SGMs off ~independence, so a
   builder paying 4.00+ is +EV — check Sportsbet/bet365. Skip below 4.00.

Do NOT bet:
- Bronze totals (either side) — model blind spot vs fully-priced angle.
- Spain & Under SGM — legs fight each other (fair 5.23, books pay ~4.3).
- England at 3.8x — model has them 16-25%, no engine support.

## Engine receipts

- SGM M104 home+over: true 0.2681 vs naive 0.2127, corr +26.0%, fair 3.73
- SGM M104 home+under: true 0.1911 vs naive 0.2464, corr -22.5%, fair 5.23
- Multi FRA+ESP: combined 0.2615, fair 3.82, slip 4.416, EV +0.155
- Multi FRA+O2.5: combined 0.2639, fair 3.79, slip 4.32, EV +0.140
