"""Tests for the Platt-scaling calibration layer.

Pins three invariants:
  1. Identity params = no-op (predictions pass through unchanged).
  2. Outputs always sum to 1.0 and stay in [0, 1].
  3. Fitting on the audit's miscalibration pattern produces parameters that
     materially close the +16/-16pp gap on the wing bands. This is the
     regression guard for the 2026-06-30 audit results.
"""
from __future__ import annotations

import math
import os
import random
import tempfile
from pathlib import Path

import pytest

from backend.models import platt_calibration as platt


@pytest.fixture(autouse=True)
def isolated_state(monkeypatch):
    """Each test gets its own params file so they can't cross-contaminate."""
    tmp = tempfile.mkdtemp()
    monkeypatch.setenv("WC26_STATE_DIR", tmp)
    monkeypatch.delenv("WC26_PLATT_CALIBRATION", raising=False)
    platt.reset_cache()
    yield Path(tmp)
    platt.reset_cache()


def _sum(t):
    return sum(t)


def test_identity_is_no_op():
    """With identity params (a=1, b=0), apply() must return the input unchanged
    up to renormalisation rounding."""
    p = platt.PlattParams.identity()
    h, d, a = platt.apply(0.5, 0.27, 0.23, p)
    assert math.isclose(h, 0.5, abs_tol=1e-6)
    assert math.isclose(d, 0.27, abs_tol=1e-6)
    assert math.isclose(a, 0.23, abs_tol=1e-6)


def test_apply_always_normalises_to_one():
    """Calibrated probabilities must sum to 1 within float tolerance, no matter
    the input or the fitted params."""
    p = platt.PlattParams(
        home=platt.PlattClassParams(a=0.7, b=0.2),
        draw=platt.PlattClassParams(a=1.3, b=-0.4),
        away=platt.PlattClassParams(a=0.5, b=0.6),
        fitted_at="x", n_samples=0, train_brier_before=0, train_brier_after=0,
    )
    rng = random.Random(42)
    for _ in range(50):
        a_, b_, c_ = rng.random(), rng.random(), rng.random()
        s = a_ + b_ + c_
        h, d, a = platt.apply(a_/s, b_/s, c_/s, p)
        assert math.isclose(h + d + a, 1.0, abs_tol=1e-9)
        for v in (h, d, a):
            assert 0.0 <= v <= 1.0


def test_too_few_samples_falls_back_to_identity():
    """Fewer than 10 settled matches → identity (don't risk overfit on noise)."""
    rows = [(0.5, 0.27, 0.23, "home"), (0.4, 0.3, 0.3, "away")]
    p = platt.fit_from_rows(rows)
    assert p.home.a == 1.0 and p.home.b == 0.0
    assert p.draw.a == 1.0 and p.draw.b == 0.0
    assert p.away.a == 1.0 and p.away.b == 0.0
    assert "too few" in p.note.lower()


def _synthetic_miscalibrated_log(n: int = 80, seed: int = 0) -> list:
    """Generate a synthetic dataset that REPLICATES the audit's pattern:
    when the model predicts ~75% for the favourite, the favourite actually
    wins ~58%; when the model predicts ~45%, the favourite actually wins
    ~62%. A correct Platt fit should learn a < 1 (shrink toward middle).
    """
    rng = random.Random(seed)
    rows = []
    for _ in range(n):
        # Pick a confidence band; for each, set true_p NOT equal to predicted_p.
        band = rng.choice(["low", "mid", "high"])
        if band == "low":
            pred_h, pred_d, pred_a = 0.45, 0.30, 0.25
            true_p_home = 0.62  # under-confident: home wins 62% when we say 45%
        elif band == "mid":
            pred_h, pred_d, pred_a = 0.55, 0.27, 0.18
            true_p_home = 0.56  # well calibrated
        else:  # high
            pred_h, pred_d, pred_a = 0.75, 0.18, 0.07
            true_p_home = 0.58  # over-confident: home wins 58% when we say 75%
        # Sample the actual outcome by the TRUE probabilities — for these
        # synthetic rows draw_prob and away_prob aren't separately modelled
        # so split the remainder evenly.
        true_p_draw = (1 - true_p_home) / 2
        # true_p_away absorbs the residual implicitly
        r = rng.random()
        if r < true_p_home:
            outcome = "home"
        elif r < true_p_home + true_p_draw:
            outcome = "draw"
        else:
            outcome = "away"
        rows.append((pred_h, pred_d, pred_a, outcome))
    return rows


def test_fit_recovers_shrinkage_on_audit_pattern():
    """The audit signal: predicted 75% wins 58%, predicted 45% wins 62%. A
    Platt fit must learn the home-class a < 1 (compresses the logit range,
    pulling both wing bands toward the middle).
    """
    rows = _synthetic_miscalibrated_log(n=200, seed=7)
    p = platt.fit_from_rows(rows)
    assert p.n_samples == 200
    # Home a must be < 1 (compression). The exact value depends on the synthetic
    # noise but the qualitative direction must be right.
    assert p.home.a < 0.9, f"home a = {p.home.a} — fit did not compress the logit range"
    # And the in-sample Brier must improve. (In-sample, sure, but the audit
    # already accepted that risk.)
    assert p.train_brier_after < p.train_brier_before, (
        f"Platt fit did not reduce Brier: before={p.train_brier_before:.4f} "
        f"after={p.train_brier_after:.4f}"
    )


def test_fit_compresses_the_wing_bands_after_apply():
    """Concrete check on the audit pattern: a 75% pre-Platt prediction should
    move toward the middle (down to <72%), and a 45% pre-Platt should move up.
    """
    rows = _synthetic_miscalibrated_log(n=200, seed=11)
    p = platt.fit_from_rows(rows)

    high_h, _, _ = platt.apply(0.75, 0.18, 0.07, p)
    low_h, _, _ = platt.apply(0.45, 0.30, 0.25, p)

    assert high_h < 0.72, f"75% prediction should be shrunk, got {high_h:.3f}"
    assert low_h > 0.48, f"45% prediction should be lifted, got {low_h:.3f}"


def test_persistence_roundtrip(isolated_state):
    """save -> load must reproduce the fitted params exactly."""
    rows = _synthetic_miscalibrated_log(n=200, seed=3)
    p = platt.fit_from_rows(rows)
    platt.save_params(p)
    platt.reset_cache()
    reloaded = platt.load_params()
    assert math.isclose(reloaded.home.a, p.home.a, abs_tol=1e-9)
    assert math.isclose(reloaded.home.b, p.home.b, abs_tol=1e-9)
    assert math.isclose(reloaded.draw.a, p.draw.a, abs_tol=1e-9)
    assert reloaded.n_samples == p.n_samples


def test_feature_flag_default_off(monkeypatch):
    """Default behaviour is OFF — the operator must explicitly opt in via
    WC26_PLATT_CALIBRATION=1 before the layer applies in the live pipeline.
    """
    monkeypatch.delenv("WC26_PLATT_CALIBRATION", raising=False)
    assert platt.is_enabled() is False
    monkeypatch.setenv("WC26_PLATT_CALIBRATION", "1")
    assert platt.is_enabled() is True
    monkeypatch.setenv("WC26_PLATT_CALIBRATION", "0")
    assert platt.is_enabled() is False
