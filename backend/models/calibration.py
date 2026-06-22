"""Outcome-level calibration shrinkage for the 1X2 vector.

WHY THIS EXISTS
---------------
Dixon-Coles / Poisson goal models are well documented to be miscalibrated at
the *outcome* level in two specific, repeatable ways (Frontiers 2025 Bundesliga
xG study; Wilkens 2026 "Can simple models predict football"; Towards Data
Science WC ML study; sports-ai.dev calibration writeup):

  1. They UNDER-PREDICT DRAWS. The DC `rho` correction only lifts the four
     low-score cells (0-0, 1-0, 0-1, 1-1); it does not fix the broader draw
     deficit that shows up once you aggregate the score matrix into 1X2. Real
     neutral-venue international football draws ~26-28% of the time; raw DC
     output for an evenly-matched game often prints a draw prob in the low 20s.

  2. They are OVERCONFIDENT in the mid band. When the model's top outcome sits
     in the 0.35-0.65 range, the realised frequency is consistently lower than
     predicted — the classic "edge filter precision" killer for value betting.

We already MEASURE both via calibration_logger (Brier, log-loss). This module
is the missing feedback step: a small, conservative, monotonic shrink applied
to the 1X2 vector AFTER the score matrix and BEFORE the market blend.

DESIGN PRINCIPLES
-----------------
- Conservative by default. Every constant is tuned to *narrow* the documented
  gap, never to invent a new opinion. With the defaults a near-even match gets
  its draw nudged up a couple of points and a runaway favourite gets pulled a
  point or two toward the field — nothing aggressive.
- Pure + deterministic. No DB, no I/O. Trivially unit-testable, which is how we
  guarantee it can only ever help (the tests assert draw-prob never decreases
  for even games and the favourite never inflates).
- Single source of truth. Both the live route and the offline prediction logger
  call this so the public track record and the UI score the identical engine.

The two knobs:
  DRAW_TARGET     empirical neutral-international draw base rate (~0.27).
  DRAW_PULL       how hard to pull the draw toward DRAW_TARGET, scaled by how
                  even the match is (even games get the full pull; lopsided
                  games get almost none — a 90% favourite SHOULD have a low draw).
  FAV_TEMP        temperature (>1) that softens the favourite/underdog split in
                  the mid band. 1.0 = off. Defaulted just above 1 so extreme
                  confidence is gently deflated toward the outcome mean.
"""
from __future__ import annotations

# Empirical draw base rate for neutral-venue senior international football.
# Sourced from public WC + qualifier aggregates (~26-28% across recent cycles).
# The draw nudge targets this only to the extent the match is evenly poised.
DRAW_TARGET = 0.27

# Fraction of the gap (DRAW_TARGET - model_draw) we close for a perfectly even
# match. Scaled down by match lopsidedness so favourites keep their low draw.
# 0.35 means: an even game whose model draw is 0.22 moves to ~0.235 (a ~1.5pt
# lift), not all the way to 0.27. Deliberately gentle.
DRAW_PULL = 0.35

# Temperature applied to the home/away split (the non-draw mass). >1 softens
# overconfident favourites toward 50/50 of the remaining mass; 1.0 disables it.
# 1.06 trims roughly 1-2 points off a strong favourite — the documented mid-band
# overconfidence cure — without flattening genuine mismatches.
FAV_TEMP = 1.06

# Below this |p_home - p_away| the match counts as "even" and gets the full
# draw pull. Above ~0.5 (a clear favourite) the pull tapers to near zero.
EVEN_SPLIT_FULL = 0.10
EVEN_SPLIT_NONE = 0.55


def _evenness(p_home: float, p_away: float) -> float:
    """1.0 for a dead-even match, 0.0 for a lopsided one. Linear taper between
    EVEN_SPLIT_FULL and EVEN_SPLIT_NONE on |p_home - p_away|."""
    gap = abs(p_home - p_away)
    if gap <= EVEN_SPLIT_FULL:
        return 1.0
    if gap >= EVEN_SPLIT_NONE:
        return 0.0
    return 1.0 - (gap - EVEN_SPLIT_FULL) / (EVEN_SPLIT_NONE - EVEN_SPLIT_FULL)


def calibrate_1x2(
    p_home: float,
    p_draw: float,
    p_away: float,
    draw_target: float = DRAW_TARGET,
    draw_pull: float = DRAW_PULL,
    fav_temp: float = FAV_TEMP,
) -> tuple[float, float, float]:
    """Return a calibrated (p_home, p_draw, p_away) that always sums to 1.

    Steps (order matters):
      1. Temperature-soften the home/away split to deflate mid-band
         favourite overconfidence (only the non-draw mass is reshaped, so the
         draw probability is untouched by this step).
      2. Pull the draw toward the empirical base rate, scaled by how even the
         match is, and renormalise. Lopsided games are barely affected.

    Inputs are assumed to be a valid probability vector (sums ~1, all >= 0).
    Degenerate inputs are returned unchanged.
    """
    s = p_home + p_draw + p_away
    if s <= 0:
        return p_home, p_draw, p_away
    # Normalise defensively.
    ph, pdr, pa = p_home / s, p_draw / s, p_away / s

    # --- Step 1: temperature on the home/away split -------------------------
    # Reshape only the non-draw mass so the draw is preserved here.
    non_draw = ph + pa
    if fav_temp != 1.0 and non_draw > 0:
        # Work in the conditional home-share, soften it toward 0.5.
        hs = ph / non_draw
        # Temperature on a 2-class softmax is equivalent to raising the odds
        # ratio to 1/T. hs' = hs^(1/T) / (hs^(1/T) + (1-hs)^(1/T)).
        inv_t = 1.0 / fav_temp
        a = hs ** inv_t
        b = (1.0 - hs) ** inv_t
        hs_soft = a / (a + b) if (a + b) > 0 else hs
        ph = non_draw * hs_soft
        pa = non_draw * (1.0 - hs_soft)

    # --- Step 2: draw pull toward the base rate -----------------------------
    even = _evenness(ph, pa)
    if even > 0 and draw_pull > 0:
        target = pdr + draw_pull * even * (draw_target - pdr)
        # Only ever LIFT the draw toward the target for even games when the
        # model under-shot it; never pull a high model draw down below target.
        if target > pdr:
            delta = target - pdr
            # Take the delta proportionally from home/away so the vector stays
            # normalised and the favourite ordering is preserved.
            pool = ph + pa
            if pool > 0:
                ph -= delta * (ph / pool)
                pa -= delta * (pa / pool)
                pdr = target

    # Final renormalise (guards against float drift).
    s2 = ph + pdr + pa
    if s2 <= 0:
        return p_home, p_draw, p_away
    return ph / s2, pdr / s2, pa / s2
