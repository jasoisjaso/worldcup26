# Site assessment — quick decision-making + model calibration

Date: 2026-06-26
Focus: what can be made better, ranked by impact-to-effort. Two themes: how
fast a visiting punter can get from "what should I bet on right now?" to a
defensible single action, and how trustworthy the underlying probabilities
are.

## What is already strong (do not break)

- Public proper-scoring-rule report card (Brier, RPS, log loss, calibration
  error, CLV). Most predictor sites do not show any of these.
- "Honest record" framing: every prediction is stamped with the model version
  that made it; speculative picks are kept OUT of the official grade.
- Match page exposes model-vs-bookmaker delta plainly and tags low-confidence
  cases ("Two model views disagree, lower confidence").
- Crowd Pulse + injury layer + live tracker are differentiators no other WC
  site has.
- The just-shipped Solid/Balanced/Bold acca tabs with Whelan size verdict are
  rare anywhere in the industry, let alone a free site.

## What the report card itself is telling us (numbers from /performance, live)

- Hit rate 51% on 55 settled.
- ROI +20.5% flat stakes, ±40.7% 95% CI. The CI is so wide the ROI is not yet
  statistically distinguishable from zero.
- Brier 0.565 on 1X2 (54 matches).
- Calibration error 0.133 on 1X2. Reference: <0.05 = well calibrated.
  O/U 2.5 is at 0.063 (good). BTTS 0.104 (borderline).
- CLV -3.5%, only 21% of picks beat the close. The site itself flags this
  on /predictions: "Treat the win rate and ROI below as noise until closing-
  line value turns positive."
- Letter grade C from the site's own calibration heuristic.

Bottom line on the model: the directional signal is right (the favourite the
model picks does win 71% of the time, same as the market), but the
PROBABILITIES being assigned to those outcomes are systematically off. That
miscalibration is exactly what bleeds the edge into the closing line.

## Decision-speed: where the friction is

(Friction noted from walking the live site as a first-time punter with five
minutes to find one bet.)

D1. Homepage is a tournament browser, not an action surface. To get from
    "I just opened the site" to "I'm at the bookmaker placing a bet" the
    fastest path is: scroll past the 24 fixtures, find the nav, click
    Picks > Model Picks, scroll, copy. There is no "tonight's top pick"
    card at the top of /.

D2. The match page is information-dense to the point of indecision. Japan
    vs Sweden has 15+ sections (header, models-disagree warning, stake
    suggestion, goals, cards, subs, top performer, what's at stake, season
    form, head-to-head, absences, live win probability chart, factor
    contributions, key players, model-vs-market grid, scoreline heatmap,
    total goals dist, team comparison, every market with fair odds, corners,
    cards, anytime scorers). The page has the answer; the answer is just
    buried. Good news: the "Edge on Japan. Model has Japan at 57%. Bookies
    imply 48%. 9-point gap" line is already at the top. We just need to
    treat that line as the page's primary surface, not a paragraph.

D3. The acca builder's Build-Your-Own tab requires building from scratch.
    There's no "import the Balanced model pick and tweak from there"
    button. Power users want a starting point.

D4. /winner is a flat list of 48 teams in 5 buckets. No view of "where do
    our outright odds disagree most with the market?". The user has to
    cross-reference /winner with bookmaker odds by hand.

D5. /value is good, but to actually act on a pick the user has to manually
    take note of the match, market, stake %, best book. There's no
    one-tap share-to-clipboard slip the user can paste at a bookmaker, no
    "pin this pick" so it's there on next visit.

D6. Live banner shows live in-play matches but the action ("here's the LIVE
    edge our model sees right now vs the live market") isn't surfaced as
    an action.

## Calibration: where the model is leaking EV

C1. No automated recalibration loop. The codebase has a calibration LOGGER
    (backend/data/calibration_logger.py — Brier + log loss + favourite-
    correct per settled match) but no recalibration MAPPING. Industry best
    practice (the sports-ai.dev guide is representative) is to fit an
    isotonic regression or Platt-scaled logistic on a holdout set and
    apply it as a transformation between raw model probability and served
    probability. The site does not currently do this. The model produces
    a raw Dixon-Coles probability and serves it.

C2. 1X2 calibration error 0.133. The fix is a per-market recalibration
    table. With 54 graded matches the holdout sample is small but workable
    for isotonic regression on 3 outcomes.

C3. Per-market calibration disparity. O/U 2.5 is at 0.063, 1X2 is at 0.133.
    Recalibration would lift 1X2 to roughly O/U 2.5 levels. The
    EV-attribution box on every match page would become more honest, and
    the Solid/Balanced/Bold acca picker would become sharper because its
    geomean-per-leg threshold is computed off the same probabilities.

C4. Negative CLV is the canary. The model says price is 1.91, you log it at
    1.91, but by kickoff the sharp closing price is 1.85. We were chasing
    a vig the market already corrected. Two causes that explain most of it:
      (a) the model is overconfident on extreme tails (0.65+ probabilities
          land less often than stated) — exactly the segment your value
          board mostly fires on, and
      (b) we are pricing against the median of three soft books (Bet365,
          Sportsbet, Unibet) but the closing price is sharp — we are
          measuring our edge vs a noisier signal than the close.

C5. The "rolling Brier" trend on /performance (0.195 → 0.132 over last 10)
    is positive but it is the model getting more DATA, not the model getting
    recalibrated. A proper recalibration loop would skip the model straight
    to its asymptote. The current curve is "model improves as the
    tournament progresses". The desired curve is "model is well-calibrated
    from MD2 onwards because we recalibrate weekly".

C6. There is no Shin-devig comparison applied to closing-line snapshots
    for calibration's sake. We have devig_shin in the codebase already (used
    for the value board's market-implied probabilities). Applying it to the
    closing line and re-running Brier vs the devigged close would give a
    second calibration metric ("vs the sharp probability we think is true")
    that is more useful than Brier vs realised result alone.

# Prioritised recommendations

Ranked by impact-per-hour. "Impact" = how much it moves the needle on the
user's stated goals (quick decisions OR a sharper model). "Effort" = a rough
afternoon-shift estimate.

## Quick decision-making

QD1 (impact: high, effort: 30 min)
"Top pick right now" card at the top of /. One card showing the Balanced
2-leg slip from /acca?obj=balanced AND the single highest-Kelly value pick
from /value. Each with the best book + the stake % + a one-tap copy.
This is the missing "I just opened the site, what do I bet" surface. The
data + the picker are already there; we just need to render them on the
home page above the fixtures list.

QD2 (impact: high, effort: 1 hr)
Match page "Verdict card" promoted to the page's primary block. Take the
existing "Edge on Japan. Model has Japan at 57%. Bookies imply 48%. 9-pt
gap." paragraph + the stake recommendation + the best book + the Whelan
verdict (carry it over from /acca metadata) and put it in a single sticky
card at the top. Everything else stays below as "deep dive". The information
density doesn't go down, but the decision path does — top 200px of the page
is "should I bet, what, where, how much".

QD3 (impact: medium, effort: 1 hr)
Acca builder "Use the model's Balanced slip as a starting point" button on
/acca?tab=custom. Pre-fills MultiBuilder with the current Balanced picks so
the user can tweak from a strong base instead of building from scratch.

QD4 (impact: medium, effort: 2 hr)
/winner "Outright value board" tab. For each team show: model% vs implied
% from the highest-priced bookmaker (use existing OddsAPI plumbing if we
fetch outrights, or fall back to the bookmaker's own outright table). Sort
by edge. Adds a futures-betting decision surface we don't currently have.

QD5 (impact: medium, effort: 2 hr)
"Quick share slip" on every value pick / acca card. Generates a
text-copyable line: "WC26 Pick: Japan O2.5 @ 1.91 (Unibet) — model 66%,
+20.6% EV, 3.8% stake". Adds a tap-to-copy. Power users will paste this
into Telegram chat / Discord / their own notes, which doubles as free
referral marketing.

QD6 (impact: low, effort: 4 hr)
"My Picks" pin-and-track. The /my-picks route already exists. Add a
"pin this pick to track it" button on every value card so the user's
visit on day 2 lands them on "your 3 pinned picks, here's where they
stand now" instead of a fresh page.

## Calibration

CAL1 (impact: high, effort: 4 hr) — biggest unfair win
Per-market isotonic-regression recalibration of model probabilities,
fitted on the settled-match calibration log and re-fitted weekly.

  - Holdout split: train the model as-is, fit isotonic on the last 30 days
    of settled matches, apply the mapping to served probabilities for the
    next 7 days. Re-fit weekly.
  - Per market: separate mappings for home_win, draw, away_win, over_2_5,
    under_2_5, btts, btts_no. The infrastructure (PredictionSnapshot +
    ModelCalibrationLog) already stores everything we need.
  - Store BOTH raw_p and calib_p in PredictionSnapshot so the report card
    can show "calibration was X before, Y after this recalibration".
  - Expected outcome: 1X2 ECE drops from 0.133 toward 0.07-0.08 (O/U 2.5
    level). Real downstream effect: the value board stops flagging false
    edges in the 60-75% probability band where the model is most overconfident.
  - Code home: new `backend/models/recalibration.py`. Hook into
    `backend.api.routes.predictions._build_prediction` after raw Poisson
    grid is computed.

CAL2 (impact: medium, effort: 2 hr)
Closing-line-anchored Brier as a SECOND calibration metric.

  - For each picked match, snapshot the de-vigged Shin-fair closing price.
    Compute Brier on the model's pre-kickoff p vs the de-vigged closing p
    (a "vs the sharp market" calibration), not just vs the realised result.
  - This metric trains a lot faster than realised-result Brier (every
    match contributes to it, not just settled ones), and is closer to the
    business-relevant signal (would a sharp punter have taken our price?).
  - Show it next to realised-Brier on /performance.

CAL3 (impact: medium, effort: 1 hr)
Per-confidence-band CLV breakdown.

  - The confidence-band reliability code is already there
    (calibration_logger.confidence_band_record). Extend it to compute CLV
    per band: "in the 70-85% band the model lost -8% to the close, in the
    50-60% band it gained +2%".
  - This identifies WHICH probability range the model is overconfident in
    — the actionable input to CAL1.

CAL4 (impact: medium, effort: 30 min)
Pin the Brier-trend chart caption to "model is sharpening AS the tournament
progresses". Currently the trend (0.195 → 0.132 over last 10) suggests the
model is learning. After CAL1 ships, the trend will collapse to a flat
line — recalibration wipes that learning curve out. We should reframe the
trend chart accordingly.

CAL5 (impact: high, effort: 4 hr) — model upgrade, not just calibration
Sharp-anchor blending in the underlying Dixon-Coles fit. We already have
sharp_anchor_for() in the data fetcher (Pinnacle). Use it as a SOFT
constraint on the DC ratings refit — penalise DC fits that produce
probabilities far from the Pinnacle close on common-opponent matches. This
is upstream of CAL1; the two stack.

CAL6 (impact: low, effort: 2 hr)
Beta calibration for the OUTRIGHT distribution. The 8.7-pts Argentina
title number on /winner has no calibration trace. Tournament outrights
are hard because each tournament is one observation, but a Beta-distribution
calibration on the per-team simulation-derived probabilities vs the
de-vigged market futures market is a cheap improvement.

# Suggested ship order

Week 1 (this week, ~4-6hr total):
  - QD1: "Top pick right now" card on /
  - QD2: Match-page verdict card
  - CAL2: Closing-line-anchored Brier
  - CAL3: Per-band CLV

Week 2 (~6hr total):
  - CAL1: Per-market isotonic recalibration loop. The biggest single
    win on the model side. Likely to flip CLV positive within 2 weeks.
  - QD3: Custom-acca "start from balanced" button

Week 3+ (~4hr each):
  - QD4: Outright value board on /winner
  - QD5: Quick share slip
  - CAL5: Sharp-anchor blend in DC fit

# Anti-recommendations (do NOT do these)

- Do NOT add corner / card markets to the value board. The expected-corners
  and expected-cards Poissons in the prediction object are guesses, not
  fitted models. The acca spec already correctly excludes them. They'd
  pollute the calibration trend.
- Do NOT add steam / line-movement indicators to the picker. The whole
  product's value is the INDEPENDENT model finding where it DISAGREES with
  the close. Steam-following dilutes that.
- Do NOT promote multis longer than 3 legs in the model picks. The Whelan
  table says they almost never beat the shorter version. Solid and Bold
  already cap at 3; Balanced caps at 4. Keep it.
- Do NOT add a free-text "AI insight" generator on the match page. The
  page is already saturated with model output; one more "Japan is in form
  and the rivalry has produced..." paragraph is the kind of slop that
  erodes the site's honest tone.

# Research sources

- sports-ai.dev: "AI Model Calibration: Brier Score, Reliability Curves
  & Sustainable Betting Edge" — Hybrid recommendation
  (Temperature scale → Isotonic).
- Wilkens 2026, Sage Journals: "Can simple models predict football — and
  beat the odds?" — isotonic regression on Bundesliga xG-based model
  recovered ROI lost to miscalibration.
- ggbettings.com: "Top Statistical Models Every Serious Sports Bettor
  Should Know" — Platt scaling and isotonic regression on a separate
  validation fold as standard practice.
- Whelan 2026 (already in docs/research/2026-06-26_model-picks-revamp.md):
  the table that justifies Solid/Balanced/Bold leg caps.
- testpapas.com + developers.dev — sportsbook UX research on
  decision-speed and contextual menus.
