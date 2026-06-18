"""In-play win probability simulator.

Restarts the Dixon-Coles Monte Carlo from the current match state (score, elapsed
minutes, red cards) instead of from pre-match. Used by the live swing chart.

Methodology (Sportmonks / Opta / FiveThirtyEight pattern):

  1. Pre-match λ_home and λ_away are produced by the existing Dixon-Coles model.
  2. Convert to per-minute rates: λ_per_min = λ_full / 90.
  3. Adjust for red cards: a 10-man side typically scores ~70% as often, its opponent
     ~120%. (Empirical from Opta's published in-play model.)
  4. For the remaining minutes, simulate N=10,000 Bernoulli draws per team per minute.
  5. Add observed goals to the simulated remaining goals → final scoreline.
  6. Tally win/draw/loss across N sims.

The simulator is decoupled from data fetching and DB — pure function, deterministic
under a seed, fast (<100ms for 10k sims on the VPS).
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


# Empirical per-minute rate multipliers when a team has a one-man deficit.
# Source: Opta's published in-play methodology; corroborated by Premier League studies.
RED_CARD_SHORT_SIDE_MULT = 0.70
RED_CARD_LONG_SIDE_MULT = 1.20
MAX_TOTAL_MINUTES = 95  # 90 + typical stoppage; we cap to avoid runaway sims


@dataclass(frozen=True)
class LiveState:
    """A snapshot of the match at a given minute."""

    elapsed_min: int          # 0..95
    home_score: int
    away_score: int
    home_red_cards: int = 0   # cumulative red cards against home
    away_red_cards: int = 0


@dataclass(frozen=True)
class LiveWP:
    """Live win-probability tuple at a given minute."""

    p_home: float
    p_draw: float
    p_away: float

    def as_dict(self) -> dict:
        return {"p_home": round(self.p_home, 4),
                "p_draw": round(self.p_draw, 4),
                "p_away": round(self.p_away, 4)}


def _adjust_rates(
    lam_home_per_min: float,
    lam_away_per_min: float,
    home_red_cards: int,
    away_red_cards: int,
) -> tuple[float, float]:
    """Apply red-card adjustment to per-minute scoring rates.

    Each net red card against a side multiplies their rate by `RED_CARD_SHORT_SIDE_MULT`
    and their opponent's by `RED_CARD_LONG_SIDE_MULT`. Multiple reds stack
    multiplicatively (an 8-man side is in deep trouble).
    """
    net_h = home_red_cards - away_red_cards
    if net_h > 0:
        h_mult = RED_CARD_SHORT_SIDE_MULT ** net_h
        a_mult = RED_CARD_LONG_SIDE_MULT ** net_h
    elif net_h < 0:
        h_mult = RED_CARD_LONG_SIDE_MULT ** (-net_h)
        a_mult = RED_CARD_SHORT_SIDE_MULT ** (-net_h)
    else:
        h_mult = a_mult = 1.0
    return lam_home_per_min * h_mult, lam_away_per_min * a_mult


def simulate_live_wp(
    lambda_home: float,
    lambda_away: float,
    state: LiveState,
    *,
    n_sims: int = 10_000,
    seed: int | None = None,
) -> LiveWP:
    """Restart the model from the current match state and return win/draw/away probs.

    Args:
        lambda_home: pre-match expected home goals for the FULL 90 minutes.
        lambda_away: pre-match expected away goals for the FULL 90 minutes.
        state: current score, elapsed minute, red cards.
        n_sims: Monte Carlo iterations. 10k is enough for ±0.5pt accuracy.
        seed: RNG seed for reproducibility (tests).

    Returns:
        LiveWP with p_home + p_draw + p_away ≈ 1.
    """
    rng = np.random.default_rng(seed)

    minutes_remaining = max(0, MAX_TOTAL_MINUTES - state.elapsed_min)
    if minutes_remaining == 0:
        # Match is over (or treated as over) — return the observed result.
        if state.home_score > state.away_score:
            return LiveWP(1.0, 0.0, 0.0)
        if state.home_score < state.away_score:
            return LiveWP(0.0, 0.0, 1.0)
        return LiveWP(0.0, 1.0, 0.0)

    lam_h_per_min = lambda_home / 90.0
    lam_a_per_min = lambda_away / 90.0
    lam_h_per_min, lam_a_per_min = _adjust_rates(
        lam_h_per_min, lam_a_per_min,
        state.home_red_cards, state.away_red_cards,
    )

    # Vectorised Poisson draw: each sim's remaining goals follow Poisson(lambda * minutes).
    # We sum the per-minute Bernoulli into a single Poisson per side per sim — same
    # distribution, far faster than minute-by-minute.
    lam_h_rem = lam_h_per_min * minutes_remaining
    lam_a_rem = lam_a_per_min * minutes_remaining

    rem_h = rng.poisson(lam_h_rem, size=n_sims)
    rem_a = rng.poisson(lam_a_rem, size=n_sims)

    final_h = state.home_score + rem_h
    final_a = state.away_score + rem_a

    p_home = float((final_h > final_a).mean())
    p_away = float((final_h < final_a).mean())
    p_draw = 1.0 - p_home - p_away
    return LiveWP(p_home, p_draw, p_away)


def simulate_swing_chart(
    lambda_home: float,
    lambda_away: float,
    timeline: list[LiveState],
    *,
    n_sims: int = 10_000,
    seed: int | None = None,
) -> list[tuple[int, LiveWP]]:
    """Compute the swing-chart series for a full match timeline.

    `timeline` is a list of `LiveState` at each minute we want a tick for (typically
    every 5 minutes plus every event). Returns `[(elapsed_min, LiveWP), ...]`.
    """
    return [(state.elapsed_min, simulate_live_wp(
        lambda_home, lambda_away, state, n_sims=n_sims, seed=seed,
    )) for state in timeline]
