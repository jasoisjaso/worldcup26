"""Empirical Platt scaling layer for the 1X2 prediction vector.

Why this exists
---------------
The theory-driven `calibrate_1x2` in calibration.py addresses two documented
biases (DC draw deficit, mid-band favourite overconfidence) with fixed
constants. The calibration audit on 2026-06-30 (n=74 settled WC2026 matches)
showed a residual miscalibration that the fixed-constant layer doesn't catch:

    band      predicted   hit    delta
    40-50%      46%       62%    +16pp under-confident
    70-80%      74%       59%    -16pp over-confident
    middle (50-70%):     well calibrated
    extremes (33-40, 80+): borderline, small sample

The fix is Platt scaling: a per-class logistic regression of
`logit(predicted_p) -> logit(true_p)` fitted on the calibration log. Applied
AFTER `calibrate_1x2`, before any downstream consumer reads the probabilities.

Design
------
- Per-class fit (home / draw / away independently). Multi-class with
  re-normalisation. Each class gets two parameters (a, b) for
  `p_calibrated = sigmoid(a * logit(p_raw) + b)`.
- Fitted from `model_calibration_log` joined to `matches`. Settled matches
  only; in-sample for now (n=74 is too small for hold-out). The audit doc
  acknowledges in-sample fit risk.
- Cached as a single JSON file at `<state_dir>/platt_params.json` so the
  fit cost is paid once, then applied per prediction. Refit on demand via
  the admin route, or on a nightly schedule once we have it.
- Feature flag `WC26_PLATT_CALIBRATION` (default OFF) so we can deploy and
  verify the dry-run output (Brier delta logged) before flipping default ON.

Math
----
For each class c:
  logit(p_c_raw)  -> sigmoid(a_c * logit(p_c_raw) + b_c)
fitted by minimising NLL on the per-class binary outcome (won/didn't win
for class c). After applying per-class, the three calibrated probabilities
are renormalised to sum to 1.

The fit uses scipy.optimize.minimize with the sigmoid log-likelihood.
"""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


_EPS = 1e-6
_DEFAULT_PARAMS_FILE = "platt_params.json"


def _logit(p: float) -> float:
    """Clamped logit. Inputs in [eps, 1-eps] guard against -inf/+inf."""
    p = max(_EPS, min(1.0 - _EPS, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


@dataclass
class PlattClassParams:
    """Two scalars per class: sigmoid(a * logit(p_raw) + b)."""
    a: float
    b: float


@dataclass
class PlattParams:
    """Fitted Platt parameters for the 1X2 vector + bookkeeping."""
    home: PlattClassParams
    draw: PlattClassParams
    away: PlattClassParams
    fitted_at: str           # ISO 8601 UTC
    n_samples: int           # how many calibration_log rows the fit saw
    train_brier_before: float  # mean Brier on training set BEFORE Platt
    train_brier_after: float   # mean Brier on training set AFTER Platt
    note: str = ""

    @classmethod
    def identity(cls) -> "PlattParams":
        """(a=1, b=0) per class = no change. Used when no fit is available."""
        i = PlattClassParams(a=1.0, b=0.0)
        return cls(
            home=i, draw=i, away=i,
            fitted_at=datetime.now(timezone.utc).isoformat(),
            n_samples=0,
            train_brier_before=0.0,
            train_brier_after=0.0,
            note="identity (no fit yet)",
        )


# In-memory cache; lazily populated on first call.
_PARAMS: Optional[PlattParams] = None


def _params_path() -> Path:
    state = os.getenv("WC26_STATE_DIR", "data")
    return Path(state) / _DEFAULT_PARAMS_FILE


def load_params() -> PlattParams:
    """Read the cached PlattParams from disk. Returns identity if missing."""
    global _PARAMS
    if _PARAMS is not None:
        return _PARAMS
    path = _params_path()
    if not path.exists():
        _PARAMS = PlattParams.identity()
        return _PARAMS
    try:
        with path.open() as f:
            raw = json.load(f)
        _PARAMS = PlattParams(
            home=PlattClassParams(**raw["home"]),
            draw=PlattClassParams(**raw["draw"]),
            away=PlattClassParams(**raw["away"]),
            fitted_at=raw["fitted_at"],
            n_samples=raw["n_samples"],
            train_brier_before=raw.get("train_brier_before", 0.0),
            train_brier_after=raw.get("train_brier_after", 0.0),
            note=raw.get("note", ""),
        )
        return _PARAMS
    except Exception as exc:
        logger.warning("platt: failed to load %s, falling back to identity: %s", path, exc)
        _PARAMS = PlattParams.identity()
        return _PARAMS


def save_params(params: PlattParams) -> None:
    """Write PlattParams JSON atomically. Updates the in-memory cache."""
    global _PARAMS
    path = _params_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w") as f:
        json.dump({
            "home": asdict(params.home),
            "draw": asdict(params.draw),
            "away": asdict(params.away),
            "fitted_at": params.fitted_at,
            "n_samples": params.n_samples,
            "train_brier_before": params.train_brier_before,
            "train_brier_after": params.train_brier_after,
            "note": params.note,
        }, f, indent=2)
    tmp.replace(path)
    _PARAMS = params


def reset_cache() -> None:
    """Force load_params() to re-read from disk on next call. Used by tests."""
    global _PARAMS
    _PARAMS = None


def apply(p_home: float, p_draw: float, p_away: float, params: Optional[PlattParams] = None) -> tuple[float, float, float]:
    """Apply Platt scaling per class, then renormalise the 3-vector to sum 1.

    With identity params (a=1, b=0) this is a no-op except for clamping.
    """
    if params is None:
        params = load_params()
    h = _sigmoid(params.home.a * _logit(p_home) + params.home.b)
    d = _sigmoid(params.draw.a * _logit(p_draw) + params.draw.b)
    a = _sigmoid(params.away.a * _logit(p_away) + params.away.b)
    s = h + d + a
    if s <= 0:
        return p_home, p_draw, p_away
    return h / s, d / s, a / s


def _fit_one_class(p_raw: np.ndarray, y: np.ndarray) -> PlattClassParams:
    """Fit (a, b) minimising NLL of sigmoid(a*logit(p_raw) + b) vs binary y.

    Uses scipy.optimize.minimize with L-BFGS-B. Small L2 penalty on (a-1, b)
    keeps the fit close to identity when the signal is weak — important at
    n=74 samples.
    """
    from scipy.optimize import minimize  # local import: scipy is heavy

    z = np.array([_logit(p) for p in p_raw])
    y = y.astype(float)

    def nll(params):
        a, b = params
        logits = a * z + b
        # log-sum-exp safe NLL
        # nll = -mean(y * log(sigmoid(l)) + (1-y) * log(sigmoid(-l)))
        #     = -mean(y * (-log(1+exp(-l))) + (1-y) * (-log(1+exp(l))))
        # Use np.logaddexp for stability.
        nll_val = float(np.mean(np.logaddexp(0.0, -logits) * y + np.logaddexp(0.0, logits) * (1 - y)))
        # L2 toward identity (a=1, b=0). Small lambda — just keeps the fit sane.
        reg = 0.01 * ((a - 1.0) ** 2 + b ** 2)
        return nll_val + reg

    res = minimize(nll, x0=[1.0, 0.0], method="L-BFGS-B", bounds=[(0.05, 5.0), (-3.0, 3.0)])
    if not res.success:
        logger.warning("platt fit did not converge: %s", res.message)
    return PlattClassParams(a=float(res.x[0]), b=float(res.x[1]))


def fit_from_rows(rows: list[tuple[float, float, float, str]]) -> PlattParams:
    """Fit PlattParams from a list of (p_home, p_draw, p_away, outcome) rows.

    outcome is one of "home", "draw", "away". Returns identity if rows is
    empty or fewer than 10 samples (below that the fit is noise-dominated).
    """
    if len(rows) < 10:
        identity = PlattParams.identity()
        identity.note = f"too few samples to fit (n={len(rows)} < 10), using identity"
        return identity

    p_h = np.array([r[0] for r in rows])
    p_d = np.array([r[1] for r in rows])
    p_a = np.array([r[2] for r in rows])
    y_h = np.array([1 if r[3] == "home" else 0 for r in rows])
    y_d = np.array([1 if r[3] == "draw" else 0 for r in rows])
    y_a = np.array([1 if r[3] == "away" else 0 for r in rows])

    home = _fit_one_class(p_h, y_h)
    draw = _fit_one_class(p_d, y_d)
    away = _fit_one_class(p_a, y_a)

    # Compute Brier before / after on the training set for diagnostics.
    def _brier(ph, pd, pa):
        out = []
        for i in range(len(rows)):
            h, d, a = ph[i], pd[i], pa[i]
            t_h = 1 if rows[i][3] == "home" else 0
            t_d = 1 if rows[i][3] == "draw" else 0
            t_a = 1 if rows[i][3] == "away" else 0
            out.append((h - t_h) ** 2 + (d - t_d) ** 2 + (a - t_a) ** 2)
        return float(np.mean(out))

    brier_before = _brier(p_h, p_d, p_a)
    cal = [apply(p_h[i], p_d[i], p_a[i], PlattParams(home=home, draw=draw, away=away, fitted_at="", n_samples=0, train_brier_before=0, train_brier_after=0))
           for i in range(len(rows))]
    cal_h = np.array([c[0] for c in cal])
    cal_d = np.array([c[1] for c in cal])
    cal_a = np.array([c[2] for c in cal])
    brier_after = _brier(cal_h, cal_d, cal_a)

    return PlattParams(
        home=home, draw=draw, away=away,
        fitted_at=datetime.now(timezone.utc).isoformat(),
        n_samples=len(rows),
        train_brier_before=brier_before,
        train_brier_after=brier_after,
        note=f"fitted on n={len(rows)} settled matches",
    )


def fit_from_db(db) -> PlattParams:
    """Fit PlattParams from the model_calibration_log table.

    Pulls only settled-match rows. Outcomes are derived from home_score vs
    away_score (the logger stores the pre-kickoff probs alongside the actual
    scoreline).
    """
    from sqlalchemy import text

    # Direct SQL — the table is wide-ish and we don't need the ORM overhead.
    sql = text("""
        SELECT l.pre_p_home, l.pre_p_draw, l.pre_p_away, l.home_score, l.away_score
        FROM model_calibration_log l
        JOIN matches m ON m.id = l.match_id
        WHERE m.status = 'complete'
          AND l.pre_p_home IS NOT NULL
          AND l.pre_p_draw IS NOT NULL
          AND l.pre_p_away IS NOT NULL
          AND l.home_score IS NOT NULL
          AND l.away_score IS NOT NULL
    """)
    rows = []
    for r in db.execute(sql).fetchall():
        p_h, p_d, p_a, hs, as_ = r
        if hs > as_: outcome = "home"
        elif hs < as_: outcome = "away"
        else: outcome = "draw"
        rows.append((p_h, p_d, p_a, outcome))

    return fit_from_rows(rows)


def is_enabled() -> bool:
    """Feature flag. Default OFF so a dry-run shows the delta before flipping."""
    return os.getenv("WC26_PLATT_CALIBRATION", "0") == "1"
