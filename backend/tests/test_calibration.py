"""Tests for the outcome-level 1X2 calibration layer (models/calibration.py).

The whole point of this layer is that it can ONLY narrow the documented
DC/Poisson miscalibration (draw deficit + mid-band favourite overconfidence),
never invent a new opinion. These tests lock that contract:

  - output is always a valid probability vector (sums to 1, all in [0,1])
  - for an EVEN match the draw is lifted (never lowered)
  - the favourite never gets MORE confident than the raw model
  - a lopsided match is left almost untouched (we don't force draws on
    genuine mismatches)
  - the favourite/underdog ORDERING is always preserved
"""
from __future__ import annotations

from backend.models.calibration import (
    DRAW_TARGET,
    calibrate_1x2,
)


def _valid(vec: tuple[float, float, float]) -> None:
    h, d, a = vec
    assert all(0.0 <= p <= 1.0 for p in (h, d, a)), vec
    assert abs((h + d + a) - 1.0) < 1e-9, f"must sum to 1, got {h + d + a}"


def test_output_is_valid_probability_vector():
    for vec in [
        (0.45, 0.27, 0.28),
        (0.80, 0.12, 0.08),
        (0.10, 0.20, 0.70),
        (0.33, 0.34, 0.33),
    ]:
        _valid(calibrate_1x2(*vec))


def test_even_match_lifts_the_draw():
    """A near-even match with an under-shot draw must get the draw nudged UP."""
    # Raw DC-style output: even home/away, draw under the base rate.
    h, d, a = 0.40, 0.20, 0.40
    ch, cd, ca = calibrate_1x2(h, d, a)
    assert cd > d, "draw should be lifted for an even match"
    assert cd <= DRAW_TARGET + 1e-9, "never lifts past the target"
    _valid((ch, cd, ca))


def test_even_match_keeps_symmetry():
    """A perfectly symmetric match stays symmetric after calibration."""
    ch, cd, ca = calibrate_1x2(0.40, 0.20, 0.40)
    assert abs(ch - ca) < 1e-9, "symmetric input must stay symmetric"


def test_favourite_never_inflates():
    """The mid-band shrink must not make a favourite MORE confident."""
    h, d, a = 0.62, 0.22, 0.16
    ch, cd, ca = calibrate_1x2(h, d, a)
    assert ch <= h + 1e-9, "favourite probability must not increase"


def test_ordering_preserved():
    """Whoever was favourite stays favourite; underdog stays underdog."""
    h, d, a = 0.55, 0.25, 0.20
    ch, cd, ca = calibrate_1x2(h, d, a)
    assert ch > ca, "home was favourite, must remain favourite"
    # And the reverse case
    ch2, cd2, ca2 = calibrate_1x2(0.18, 0.24, 0.58)
    assert ca2 > ch2, "away was favourite, must remain favourite"


def test_lopsided_match_barely_touched():
    """A genuine mismatch must NOT have a draw forced onto it."""
    h, d, a = 0.84, 0.11, 0.05
    ch, cd, ca = calibrate_1x2(h, d, a)
    # Draw moves by at most a hair (evenness ~0), favourite stays dominant.
    assert abs(cd - d) < 0.02, "lopsided match draw should be nearly unchanged"
    assert ch > 0.78, "strong favourite must remain a strong favourite"


def test_draw_not_pulled_down_when_already_high():
    """If the model already prints a high draw, we don't yank it to target."""
    h, d, a = 0.30, 0.45, 0.25  # draw already well above DRAW_TARGET
    ch, cd, ca = calibrate_1x2(h, d, a)
    assert cd >= DRAW_TARGET, "an already-high draw must not be pulled below target"


def test_degenerate_input_returned_unchanged():
    assert calibrate_1x2(0.0, 0.0, 0.0) == (0.0, 0.0, 0.0)


def test_temperature_off_is_identity_on_split():
    """With fav_temp=1 and draw_pull=0 the function is the identity (renorm)."""
    h, d, a = 0.50, 0.25, 0.25
    ch, cd, ca = calibrate_1x2(h, d, a, draw_pull=0.0, fav_temp=1.0)
    assert abs(ch - h) < 1e-9 and abs(cd - d) < 1e-9 and abs(ca - a) < 1e-9


def test_calibration_reduces_brier_on_drawish_sample():
    """End-to-end sanity: on a synthetic sample of evenly-matched games that
    actually draw more than the raw model implies, calibration should lower
    (improve) the mean Brier score. This is the whole reason the layer exists."""
    # 100 evenly-matched fixtures. Raw model says draw=0.20; reality draws ~0.30.
    raw = (0.40, 0.20, 0.40)
    cal = calibrate_1x2(*raw)

    def brier(vec, outcome):
        # outcome: 0=home,1=draw,2=away
        y = [0.0, 0.0, 0.0]
        y[outcome] = 1.0
        return sum((p - t) ** 2 for p, t in zip(vec, y)) / 3.0

    # Realised distribution: 35% home, 30% draw, 35% away (draw-heavy vs model).
    outcomes = [0] * 35 + [1] * 30 + [2] * 35
    raw_brier = sum(brier(raw, o) for o in outcomes) / len(outcomes)
    cal_brier = sum(brier(cal, o) for o in outcomes) / len(outcomes)
    assert cal_brier < raw_brier, (
        f"calibration should improve Brier on a draw-heavy sample "
        f"(raw={raw_brier:.4f}, cal={cal_brier:.4f})"
    )
