"""Pick guardrails — the discipline layer that keeps the model honest.

WHY THIS EXISTS
---------------
The model lost real money on a +68% EV "Australia to beat USA" pick. That is
the textbook +EV failure the literature names bluntly: *overestimating your
edge is the fastest way to lose money*. When our model probability sits far
ABOVE a sharp market's implied probability, the overwhelmingly likely
explanation is that OUR number is wrong — the market is sharp — not that we
found free money.

The single-pick value board already computed reliability tiers
(solid/speculative/longshot) and sorted by them. But:
  - the MULTI picker ignored tiers entirely and had no upper EV cap, so a
    68% EV leg sailed straight through;
  - nothing capped an absurd absolute edge anywhere;
  - edge was measured against the SOFT book (whose vig/errors inflate phantom
    EV) even when a sharp Pinnacle line was available;
  - thin-sample teams (few fitted/archived games) could print a huge edge off
    noise.

This module centralises the fix so the value board AND the multi picker apply
the IDENTICAL discipline. Each rule is conservative and unit-tested so it can
only narrow phantom edges, never invent new ones.

THE GRADE SPLIT
---------------
Picks are classified into two buckets:
  - CORE: a believable, sample-backed, sharp-anchored edge. These are the
    picks we stand behind; they count toward the public hit-rate / ROI grade.
  - SPECULATIVE: the model sees something but we can't fully stand behind it
    (edge above the believable band, or thin sample). Surfaced separately,
    at the user's discretion, and explicitly EXCLUDED from the grade.
  - REJECT: implausible edge (above the hard cap) or longshot fantasy — never
    published at all.
"""
from __future__ import annotations

from dataclasses import dataclass

# --- Tunable thresholds ------------------------------------------------------

# Believable band: how far the model prob may exceed the (de-vigged) market
# implied prob and still count as a CORE pick we stand behind. 1.30 = the model
# rates it up to 30% more likely than the book — a defensible disagreement.
CORE_MAX_RATIO = 1.30

# Speculative band ceiling. Between CORE_MAX_RATIO and this we still SHOW the
# pick (separate tab, user discretion) but it does NOT count toward the grade.
SPECULATIVE_MAX_RATIO = 1.75

# Hard absolute-EV ceiling. A measured edge above this is treated as a red flag
# (model error / stale line), NOT a green light, regardless of ratio. 0.25 =
# 25% EV. The Australia-v-USA leg (model 0.45 vs implied ~0.27 => ~+68% EV) is
# far above this and is rejected outright.
MAX_ABSOLUTE_EV = 0.25

# Below this fitted/archived sample size for a team we don't trust a big edge —
# the model prob is shrunk toward the market before tiering so noise can't print
# a phantom edge.
MIN_TRUSTED_SAMPLE = 8

# Longshot price ceiling for CORE picks — even a "believable" ratio on a 12.0
# outsider is mostly variance. Core picks cap the book price here.
CORE_MAX_ODDS = 8.0


@dataclass(frozen=True)
class PickGrade:
    """The verdict on one candidate leg/pick."""
    tier: str          # "core" | "speculative" | "reject"
    reason: str        # human-readable why (for the UI + debugging)
    model_prob: float  # the (possibly shrunk) model probability used
    market_implied: float | None
    ev: float          # EV vs the price actually used
    counts_to_grade: bool  # True only for core


def shrink_toward_market(
    model_prob: float,
    market_implied: float | None,
    sample: int,
    min_sample: int = MIN_TRUSTED_SAMPLE,
) -> float:
    """Bayesian shrinkage of the model prob toward the market on thin samples.

    weight = n / (n + min_sample). A team with `min_sample` games gets a 50/50
    blend of model and market; large n lets the model dominate. With no market
    anchor we can't shrink, so we return the model prob unchanged.
    """
    if market_implied is None or market_implied <= 0:
        return model_prob
    n = max(0, int(sample))
    weight = n / (n + min_sample) if (n + min_sample) > 0 else 0.0
    return weight * model_prob + (1.0 - weight) * market_implied


def grade_pick(
    model_prob: float,
    market_implied: float | None,
    book_odds: float | None,
    *,
    sample: int = MIN_TRUSTED_SAMPLE * 4,  # default: trust fully unless told otherwise
    sharp_implied: float | None = None,
) -> PickGrade:
    """Classify one candidate into core / speculative / reject.

    Args:
        model_prob: the model's RAW probability for this outcome.
        market_implied: de-vigged SOFT-book implied probability (fallback anchor).
        book_odds: the decimal price we'd take (for the EV figure).
        sample: fitted/archived sample size backing this team's number.
        sharp_implied: de-vigged SHARP (Pinnacle) implied probability. When
            present it OVERRIDES market_implied as the edge anchor — sharp lines
            are the truest probability, so measuring edge against them strips out
            the soft-book noise that inflates phantom EV.

    The order of operations matters: shrink first (kill noise), then anchor to
    the sharp line, then tier by ratio, then hard-cap by absolute EV.
    """
    anchor = sharp_implied if (sharp_implied and sharp_implied > 0) else market_implied

    # 1. Shrink the model prob toward the anchor on thin samples.
    shrunk = shrink_toward_market(model_prob, anchor, sample)

    # 2. EV against the price we'd actually take.
    ev = (shrunk * book_odds - 1.0) if (book_odds and book_odds > 0) else 0.0

    # No anchor at all → we can't judge the edge; treat as speculative-info only.
    if anchor is None or anchor <= 0:
        return PickGrade(
            tier="speculative", reason="no market line to validate against",
            model_prob=shrunk, market_implied=None, ev=round(ev, 4),
            counts_to_grade=False,
        )

    ratio = shrunk / anchor

    # 3. Hard absolute-EV ceiling — implausible edge is a red flag, not a green light.
    if ev > MAX_ABSOLUTE_EV:
        return PickGrade(
            tier="reject",
            reason=f"implausible edge (+{ev * 100:.0f}% EV > {MAX_ABSOLUTE_EV * 100:.0f}% cap) — likely model error / stale line",
            model_prob=shrunk, market_implied=round(anchor, 4), ev=round(ev, 4),
            counts_to_grade=False,
        )

    # 4. Longshot fantasy — believable ratio but on a price we won't stand behind.
    if ratio > SPECULATIVE_MAX_RATIO:
        return PickGrade(
            tier="reject",
            reason=f"model {ratio:.2f}x the market — too far above a sharp line to trust",
            model_prob=shrunk, market_implied=round(anchor, 4), ev=round(ev, 4),
            counts_to_grade=False,
        )

    # 5. Speculative band: the model sees something we can't fully stand behind.
    if ratio > CORE_MAX_RATIO:
        return PickGrade(
            tier="speculative",
            reason=f"edge above the believable band ({ratio:.2f}x market) — user discretion, excluded from grade",
            model_prob=shrunk, market_implied=round(anchor, 4), ev=round(ev, 4),
            counts_to_grade=False,
        )

    # 6. Core: believable, sample-backed, anchored. Counts to the grade.
    if book_odds and book_odds > CORE_MAX_ODDS:
        # Believable ratio but a long price → demote to speculative, don't reject.
        return PickGrade(
            tier="speculative",
            reason=f"believable edge but a long price ({book_odds:.1f}) — variance-heavy, excluded from grade",
            model_prob=shrunk, market_implied=round(anchor, 4), ev=round(ev, 4),
            counts_to_grade=False,
        )

    return PickGrade(
        tier="core",
        reason=f"believable edge ({ratio:.2f}x market, +{ev * 100:.1f}% EV)",
        model_prob=shrunk, market_implied=round(anchor, 4), ev=round(ev, 4),
        counts_to_grade=True,
    )
