"""
Dixon-Coles MLE attack/defense parameter fitting from martj42 historical data.

Fits per-team α (attack) and β (defense) from 8 years of international results.
For WC (neutral venue):
  λ_home = exp(log_α_home + log_β_away)
  λ_away = exp(log_α_away + log_β_home)

Home-advantage factor (γ) is estimated during fitting but stripped for neutral-venue
WC predictions — we only care about relative team strength.

Call `await ensure_fitted()` at startup; `get_lambdas()` is sync thereafter.
Falls back to None when either team has < _MIN_MATCHES in the dataset.
"""
import asyncio
import csv
import io
import logging
import math
from datetime import datetime, timedelta

import httpx
import numpy as np
from scipy.optimize import minimize
from scipy.special import gammaln

from backend.data.fetchers.results import name_to_code, _is_friendly

_CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
# Exp decay per day for the MLE weights. 0.00325 was borrowed from club tuning
# (~30x more matches/yr); on sparse international data it over-discounts older games
# and starves the fit. Walk-forward backtest (backend/eval/backtest.py, ~1500 OOS
# matches) puts the RPS optimum at ~0.0015-0.0019/day, so we use 0.0018 (half-life
# ~1.05yr). See memory: wc2026-model-findings.
_XI = 0.0018
_FIT_YEARS = 8       # two WC cycles; with decay, older data is already downweighted
_MIN_MATCHES = 5     # teams with fewer matched rows fall back to ELO
_DC_RHO = -0.13      # Dixon-Coles low-score correction (literature consensus)
_CACHE_TTL = timedelta(hours=12)

logger = logging.getLogger(__name__)

_log_attack: dict[str, float] = {}
_log_defense: dict[str, float] = {}
_built_at: datetime | None = None
_fit_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _fit_lock
    if _fit_lock is None:
        _fit_lock = asyncio.Lock()
    return _fit_lock


def _is_stale() -> bool:
    return _built_at is None or (datetime.utcnow() - _built_at) > _CACHE_TTL


def _neg_log_likelihood(
    params_vec: np.ndarray,
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    rho: float,
) -> float:
    n = (len(params_vec) - 1) // 2
    log_alpha = params_vec[:n]
    log_beta = params_vec[n : 2 * n]
    log_gamma = params_vec[2 * n]

    lh = np.exp(log_alpha[home_idx] + log_beta[away_idx] + log_gamma)
    la = np.exp(log_alpha[away_idx] + log_beta[home_idx])

    log_p_h = home_goals * np.log(np.maximum(lh, 1e-9)) - lh - gammaln(home_goals + 1)
    log_p_a = away_goals * np.log(np.maximum(la, 1e-9)) - la - gammaln(away_goals + 1)

    tau = np.ones(len(home_goals), dtype=np.float64)
    m00 = (home_goals == 0) & (away_goals == 0)
    m10 = (home_goals == 1) & (away_goals == 0)
    m01 = (home_goals == 0) & (away_goals == 1)
    m11 = (home_goals == 1) & (away_goals == 1)
    tau[m00] = 1.0 - lh[m00] * la[m00] * rho
    tau[m10] = 1.0 + la[m10] * rho
    tau[m01] = 1.0 + lh[m01] * rho
    tau[m11] = 1.0 - rho
    tau = np.maximum(tau, 1e-9)

    nll = float(-np.sum(weights * (np.log(tau) + log_p_h + log_p_a)))
    # Soft identifiability constraint: keep means of log_alpha and log_beta near 0.
    nll += 100.0 * float(np.mean(log_alpha) ** 2)
    nll += 100.0 * float(np.mean(log_beta) ** 2)
    return nll


def _fit_sync(
    home_idx: np.ndarray,
    away_idx: np.ndarray,
    home_goals: np.ndarray,
    away_goals: np.ndarray,
    weights: np.ndarray,
    n_teams: int,
) -> np.ndarray:
    x0 = np.zeros(2 * n_teams + 1)
    x0[2 * n_teams] = math.log(1.1)  # small home-advantage init
    result = minimize(
        _neg_log_likelihood,
        x0,
        args=(home_idx, away_idx, home_goals, away_goals, weights, _DC_RHO),
        method="L-BFGS-B",
        options={"maxiter": 500, "ftol": 1e-9},
    )
    return result.x


async def ensure_fitted() -> None:
    """Download martj42 CSV and fit DC parameters if cache is stale."""
    global _log_attack, _log_defense, _built_at
    if not _is_stale():
        return
    async with _get_lock():
        if not _is_stale():
            return
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.get(_CSV_URL)
                resp.raise_for_status()
            raw = resp.text
        except Exception:
            return  # keep old params if network fails

        today = datetime.utcnow().date()
        cutoff = (today - timedelta(days=_FIT_YEARS * 365)).strftime("%Y-%m-%d")

        match_counts: dict[str, int] = {}
        raw_rows: list[tuple[str, str, int, int, float]] = []

        reader = csv.DictReader(io.StringIO(raw))
        for row in reader:
            date = row.get("date", "")
            if date < cutoff:
                continue
            try:
                hg = int(row.get("home_score", ""))
                ag = int(row.get("away_score", ""))
            except (ValueError, TypeError):
                continue
            tournament = row.get("tournament", "")
            hc = name_to_code(row.get("home_team", ""))
            ac = name_to_code(row.get("away_team", ""))
            if not hc or not ac:
                continue
            try:
                match_date = datetime.strptime(date, "%Y-%m-%d").date()
            except ValueError:
                continue
            days_ago = max(0, (today - match_date).days)
            w = math.exp(-_XI * days_ago)
            if not _is_friendly(tournament):
                w *= 2.0  # competitive matches count double
            # In-tournament boost: any FIFA World Cup match (qualifying or finals)
            # is the most relevant signal for predicting WC2026 outcomes. The
            # CSV uses "FIFA World Cup" + "FIFA World Cup qualification" labels.
            tlow = tournament.lower()
            if "world cup" in tlow:
                w *= 2.5    # WC qualifiers get ~5x base; WC finals see below
            raw_rows.append((hc, ac, hg, ag, w))
            match_counts[hc] = match_counts.get(hc, 0) + 1
            match_counts[ac] = match_counts.get(ac, 0) + 1

        # Inject our locally-known WC2026 results directly. These are usually the
        # very last matches in any model's training window — the external CSV
        # source updates ~daily, so this also closes the lag gap. Weight at 5x
        # the baseline so the model adapts within ~2-3 matches.
        try:
            from backend.db.session import SessionLocal
            from backend.db.models import Match
            db = SessionLocal()
            try:
                wc_matches = (
                    db.query(Match)
                    .filter(Match.status == "complete")
                    .filter(Match.home_score.isnot(None))
                    .filter(Match.away_score.isnot(None))
                    .all()
                )
                injected = 0
                for m in wc_matches:
                    if not m.kickoff:
                        continue
                    days_ago = max(0, (today - m.kickoff.date()).days)
                    w = math.exp(-_XI * days_ago) * 5.0  # 5x boost — actual WC games are gold
                    raw_rows.append((m.home_code, m.away_code, m.home_score, m.away_score, w))
                    match_counts[m.home_code] = match_counts.get(m.home_code, 0) + 1
                    match_counts[m.away_code] = match_counts.get(m.away_code, 0) + 1
                    injected += 1
                logger.info("DC fit: injected %d WC2026 results with 5x weight", injected)
            finally:
                db.close()
        except Exception as exc:
            logger.warning("DC fit: WC injection failed: %s", exc)

        eligible = {c for c, cnt in match_counts.items() if cnt >= _MIN_MATCHES}
        filtered = [r for r in raw_rows if r[0] in eligible and r[1] in eligible]

        if len(filtered) < 50:
            return

        teams = sorted(eligible)
        tidx = {t: i for i, t in enumerate(teams)}
        n = len(teams)

        hi = np.array([tidx[r[0]] for r in filtered], dtype=np.int32)
        ai = np.array([tidx[r[1]] for r in filtered], dtype=np.int32)
        hg = np.array([r[2] for r in filtered], dtype=np.float64)
        ag = np.array([r[3] for r in filtered], dtype=np.float64)
        ws = np.array([r[4] for r in filtered], dtype=np.float64)

        loop = asyncio.get_event_loop()
        params = await loop.run_in_executor(None, _fit_sync, hi, ai, hg, ag, ws, n)

        _log_attack = {teams[i]: float(params[i]) for i in range(n)}
        _log_defense = {teams[i]: float(params[n + i]) for i in range(n)}
        _built_at = datetime.utcnow()
        logger.info("DC fit: %d teams, %d weighted matches (xi=%s, %dyr window)",
                    n, len(filtered), _XI, _FIT_YEARS)


def get_fitted_codes() -> set[str]:
    """Team codes that currently have fitted DC params (empty before ensure_fitted)."""
    return set(_log_attack.keys())


def warn_missing(expected_codes: set[str]) -> list[str]:
    """Log a warning for any expected WC team that has no DC params (would fall back to
    ELO-only). Returns the missing codes. Call after ensure_fitted()."""
    missing = sorted(c for c in expected_codes if c not in _log_attack)
    if missing:
        logger.warning("DC fit missing %d WC team(s) — ELO-only fallback for: %s",
                       len(missing), ", ".join(missing))
    return missing


def get_lambdas(home_code: str, away_code: str) -> tuple[float, float] | None:
    """
    Neutral-venue DC lambdas. Sync — requires ensure_fitted() called first.
    Returns None if either team has no fitted parameters.
    """
    if home_code not in _log_attack or away_code not in _log_attack:
        return None
    lh = math.exp(_log_attack[home_code] + _log_defense[away_code])
    la = math.exp(_log_attack[away_code] + _log_defense[home_code])
    return (max(0.3, lh), max(0.3, la))
