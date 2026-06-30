# Calibration-by-segment audit — results

Ran 2026-06-30 against `model_calibration_log` on the live VPS DB. 74 settled
1X2 predictions (every WC2026 match up through M075 NL vs MA R16). Audit
script lives at `scripts/calibration_audit.py`; rerun with
`docker exec wc26-backend python /tmp/calibration_audit.py` after copying.

## Headline

The model is **under-confident on coinflips** and **over-confident on heavy
favourites**. The miscalibration is symmetric and large enough to act on.

| Confidence band on favourite | n | Predicted | Observed | Delta |
|---|---:|---:|---:|---:|
| 33-40% | 5 | 36.3% | 60.0% | **+23.7pp** |
| 40-50% | 13 | 45.9% | 61.5% | **+15.6pp** |
| 50-60% | 16 | 54.5% | 56.2% | +1.8 |
| 60-70% | 14 | 64.9% | 64.3% | -0.6 |
| 70-80% | 17 | 74.4% | 58.8% | **-15.5pp** |
| 80+ | 9 | 86.1% | 77.8% | -8.3 |

The 50-60 and 60-70 bands are well calibrated. The wings are not. This is
the classic "logistic too steep" pattern — Platt scaling fits it.

## Other dimensions

**By phase.** Group stage (n=70) is well calibrated (-1pp). Knockout (n=4)
is way too small to say anything. The two acted segments above are
dominated by group-stage matches because that's where the n is.

**By favourite side.** Home favourites (n=45, +1.3pp) and away
favourites (n=27, -6.8pp) are both fine. There's a hint that we
over-confidence away favourites slightly but n is too small to ship a
fix purely on this axis.

**Draws-as-favourite.** Only 2 cases. Both won. Ignore.

## Overall numbers

- **Mean Brier**: 0.1828 — decent but the wings are dragging it up
- **Mean log-loss**: 0.907 — same
- **Favorite-hit rate**: 62.2% (46/74)

For reference: a perfectly-calibrated model with the same confidence
distribution would land at Brier ~0.165. So we're losing ~0.017 of Brier
to miscalibration alone. Closing the +16/-16 gap would do most of that.

## What to ship

**Platt-scaled 1X2 correction.** Fit a logistic regression of
(predicted_p_home, predicted_p_draw, predicted_p_away) → observed
outcome on the 74 settled matches. Apply it as a post-process layer on
every pre-kickoff prediction. This:

- Shrinks the 70-80% predictions down toward ~60-65% (where they
  empirically land)
- Pulls the 40-50% predictions up toward ~60% (same)
- Leaves the well-calibrated 50-60% / 60-70% middle alone
- Doesn't change the model's ORDERING — only its confidence levels

Effort: 3-4 hours. Lives in `backend/models/calibration_layer.py`,
called from the pipeline after Dixon-Coles + xG shrinkage. Re-fit nightly
as new matches settle, weighted by recency.

**Why this is the right next move:**

1. The audit already paid for itself — we know which 2 bands are off,
   we know the direction, and the fix is a textbook one-day shift.
2. Every value pick this generates will be a degree more honest — the
   80% bands will say 65% and a punter chasing big-favourite "value"
   won't be misled.
3. Pairs cleanly with the harm-reduction posture from the
   skin-in-the-game memory (project_wc26_owner_has_skin_in_game).

## What NOT to do based on this audit

- **Don't trust the knockout numbers** (n=4). The +18pp delta on
  knockout is a coin-flip artefact. The bracket has 12 matches left;
  by SF we'll have meaningful KO calibration. Until then, treat
  knockout probabilities with the same caution as group.
- **Don't tune by side** (home vs away). Sample is too small per
  side-x-band cell. The Platt scaling will absorb whatever real
  side-side effect exists.
- **Don't re-train Dixon-Coles** on this data. DC is calibrated to the
  whole historical sample; this audit reflects a 74-match sample at
  one tournament. The right place to fix is the post-process layer,
  not the model itself.

## Cross-tab: phase × band (for the record)

```
phase     band      n   hit    p_fav   delta
group     33-40     5   60.0   36.3   +23.7
group     40-50    13   61.5   45.9   +15.6
group     50-60    13   46.2   55.1    -8.9
group     60-70    14   64.3   64.9    -0.6
group     70-80    16   62.5   74.5   -12.0
group     80+       9   77.8   86.1    -8.3
knockout  50-60     3  100.0   51.9   +48.1   (n=3, ignore)
knockout  70-80     1    0.0   71.7   -71.7   (n=1, ignore)
```

## Next step

Ship the Platt-scaling layer (item A from the harvest-to-model plan got
deferred; this audit makes item A and the calibration layer effectively
the same work). Then re-run this audit nightly via the harvester loop
and surface deltas on /admin.
