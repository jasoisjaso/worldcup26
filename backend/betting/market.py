"""Market de-vig and model<->market probability blending.

Two improvements over the previous inline blocks (predictions.py / prediction_logger.py):

1. Shin's (1992) method for removing the bookmaker margin instead of naive proportional
   normalization. Proportional de-vig (p_i = (1/o_i) / sum(1/o_j)) spreads the margin
   evenly and so systematically *over*-states longshots and *under*-states favourites
   (favourite-longshot bias). Shin attributes the margin to insider trading and recovers
   fairer probabilities, especially in the tails — which is exactly where the value board
   and acca builder operate.

2. The blend is applied to Over/Under 2.5 as well, not just 1X2, so every surfaced
   probability/EV is internally consistent (previously OU/BTTS kept full vig).

The model/market weight is a single tunable constant. It is deliberately left at the
prior 0.70 (model) until an odds-history backtest can set it empirically; see
memory: wc2026-model-findings.
"""
from __future__ import annotations

import math

# Fraction of the blend given to the model (rest to the de-vigged market).
MODEL_BLEND_WEIGHT = 0.70

# Reliability tiers for a value pick — how far the model strays ABOVE the bookie's
# implied probability. A sharp market is hard to beat, so a model claiming a team is far
# more likely than the book usually means model overconfidence (esp. longshots), not free
# money. Used by both the value board and the prediction logger to keep longshot fantasies
# out of the picks/track record. See memory: value-mode-model-edge.
RATIO_SOLID = 1.30        # model <=30% more likely than the book implies — believable
RATIO_SPECULATIVE = 1.75  # 30-75% above — possible but cautious; beyond = likely noise
TIER_RANK = {"solid": 0, "speculative": 1, "longshot": 2}


def reliability_tier(model_prob: float, odds: float) -> str:
    implied = 1.0 / odds if odds > 0 else 1.0
    ratio = model_prob / implied if implied > 0 else 1.0
    if ratio <= RATIO_SOLID:
        return "solid"
    if ratio <= RATIO_SPECULATIVE:
        return "speculative"
    return "longshot"


def devig_shin(odds: list[float | None]) -> list[float] | None:
    """Shin-method fair probabilities from decimal odds. None if odds are unusable."""
    if not odds or any(o is None or o <= 1.0 for o in odds):
        return None
    # Guard above guarantees all entries are non-None and > 1.0; narrow for the
    # type checker by binding to a local list[float] before the arithmetic.
    odds_f: list[float] = [float(o) for o in odds if o is not None]
    pi = [1.0 / o for o in odds_f]
    B = sum(pi)
    if B <= 1.0:  # no margin (or arbitrage) — just normalize
        return [p / B for p in pi]

    def shin_probs(z: float) -> list[float]:
        out = []
        for p in pi:
            num = math.sqrt(z * z + 4.0 * (1.0 - z) * p * p / B) - z
            out.append(num / (2.0 * (1.0 - z)))
        return out

    # Σ shin_probs(z) decreases monotonically in z; solve Σ = 1 by bisection.
    lo, hi = 0.0, 0.99
    for _ in range(60):
        mid = (lo + hi) / 2.0
        if sum(shin_probs(mid)) > 1.0:
            lo = mid
        else:
            hi = mid
    probs = shin_probs((lo + hi) / 2.0)
    s = sum(probs)
    return [p / s for p in probs] if s > 0 else None


# --- Closing Line Value -------------------------------------------------------------
# CLV is the single most reliable signal that a betting edge is real: the closing line is
# the sharpest publicly available probability, so a pick whose price beats the de-vigged
# close has genuinely positive expectation far sooner than win-rate can prove it. We score
# every settled pick's bet price against the closing (no-vig) probability for its market.
_CLV_GROUP: dict[str, tuple[str, ...]] = {
    "home_win": ("home_win", "draw", "away_win"),
    "draw": ("home_win", "draw", "away_win"),
    "away_win": ("home_win", "draw", "away_win"),
    "over_2_5": ("over_2_5", "under_2_5"),
}
_CLV_IDX = {"home_win": 0, "draw": 1, "away_win": 2, "over_2_5": 0}


def closing_line_value(
    market: str, bet_odds: float | None, closing_book: dict | None,
) -> tuple[float | None, float | None]:
    """(closing_decimal_odds, clv) for one pick.

    clv = p_close_fair * bet_odds - 1, i.e. the bet's expected value measured against the
    Shin-devigged closing line. Positive => we beat the close. Returns (None, None) when the
    closing line for this market isn't available (e.g. BTTS with no complementary price)."""
    if not closing_book or bet_odds is None:
        return None, None
    close_dec = closing_book.get(market)
    if close_dec is None:
        return None, None
    clv = None
    grp = _CLV_GROUP.get(market)
    if grp:
        book = [closing_book.get(k) for k in grp]
        if all(b for b in book):
            fair = devig_shin(book)
            if fair:
                p_close = fair[_CLV_IDX[market]]
                clv = round(p_close * bet_odds - 1.0, 4)
    return round(close_dec, 4), clv


def _blend(model: list[float], fair: list[float], w: float = MODEL_BLEND_WEIGHT) -> list[float]:
    mixed = [w * m + (1.0 - w) * f for m, f in zip(model, fair)]
    s = sum(mixed)
    return [m / s for m in mixed] if s > 0 else model


def blend_three_way(
    model_h: float, model_d: float, model_a: float, live_odds: dict | None,
    sharp_anchor: dict | None = None,
) -> tuple[float, float, float]:
    """Blend model 1X2 with Shin-devigged market 1X2. Returns model probs unchanged
    when no usable home/draw/away odds are present.

    `sharp_anchor` (decimal odds keyed by home_win/draw/away_win) overrides
    `live_odds` as the de-vig source when present — that's the Pinnacle/Betfair
    anchor flowing in from SportsGameOdds. Sharp lines de-vig closer to true
    closing probabilities than soft books do, so the resulting blend has a
    higher information content. Fallback to soft books is automatic when no
    sharp anchor is available for this fixture.
    """
    odds_source = sharp_anchor if sharp_anchor else live_odds
    if odds_source:
        fair = devig_shin([
            odds_source.get("home_win"),
            odds_source.get("draw"),
            odds_source.get("away_win"),
        ]) if all(odds_source.get(k) for k in ("home_win", "draw", "away_win")) else None
        if fair:
            h, d, a = _blend([model_h, model_d, model_a], fair)
            return round(h, 4), round(d, 4), round(a, 4)
    return model_h, model_d, model_a


def blend_two_way(
    model_over: float, model_under: float,
    odds_over: float | None, odds_under: float | None,
    sharp_over: float | None = None, sharp_under: float | None = None,
) -> tuple[float, float]:
    """Blend a model 2-way market (e.g. Over/Under 2.5) with its Shin-devigged odds.

    Sharp odds (Pinnacle) take precedence when provided. The same fallback
    contract as `blend_three_way` applies — soft books get used when no sharp
    anchor is present for this market.
    """
    if sharp_over and sharp_under:
        fair = devig_shin([sharp_over, sharp_under])
    else:
        fair = devig_shin([odds_over, odds_under])
    if fair:
        o, u = _blend([model_over, model_under], fair)
        return round(o, 4), round(u, 4)
    return model_over, model_under
