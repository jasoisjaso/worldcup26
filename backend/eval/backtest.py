"""Walk-forward backtest of the goal model on historical internationals.

Measures the metrics that define "best predictions":
  - RPS  (ranked probability score, ordinal 1X2 — lower is better; literature ~0.19-0.21)
  - log-loss and multiclass Brier
  - calibration (reliability: predicted prob vs observed frequency)

It reuses the *production* Dixon-Coles fit (`backend.models.dc_ratings._fit_sync`)
and the *production* score matrix (`backend.models.poisson`) so the numbers reflect
the real engine, then compares against an Elo baseline and a DC/Elo blend built from
the same data — the exact architecture the live model uses.

Run:
    python -m backend.eval.backtest                # fast default (4 cutoffs, no refit sweeps)
    python -m backend.eval.backtest --xi-sweep     # also sweep time-decay xi (slow, refits)
    python -m backend.eval.backtest --cutoffs 6 --fit-years 8

Nothing here touches the live API.
"""
from __future__ import annotations

import argparse
import csv
import io
import math
import os
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import numpy as np

from backend.models.dc_ratings import _fit_sync
from backend.models.poisson import build_score_matrix, match_probabilities
from backend.eval.scoring import outcome_index, ordinal_rps, log_loss, brier

_CSV_URL = "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
_CACHE = os.path.join(os.path.dirname(__file__), ".cache_results.csv")
_FRIENDLY_KEYWORDS = ("friendly", "unofficial")

# Production constants (mirror dc_ratings.py / poisson.py / match_context.py)
PROD_XI = 0.0018           # exp decay per day (lowered from 0.00325 after this backtest)
PROD_RHO = -0.13           # Dixon-Coles low-score correction
PROD_COMP_WEIGHT = 2.0     # competitive matches weighted double
PROD_MAX_GOALS = 8
ELO_BASE_GOALS = 1.3       # elo_model.BASE_GOALS
ELO_SCALE = 2.0            # elo_model.SCALE
LAMBDA_FLOOR = 0.2


# --------------------------------------------------------------------------- data

@dataclass
class Match:
    d: date
    home: str
    away: str
    hg: int
    ag: int
    friendly: bool
    neutral: bool


def _is_friendly(tournament: str) -> bool:
    t = tournament.lower()
    return any(k in t for k in _FRIENDLY_KEYWORDS)


def load_matches(force_download: bool = False) -> list[Match]:
    raw: str | None = None
    if not force_download and os.path.exists(_CACHE):
        with open(_CACHE, "r", encoding="utf-8") as f:
            raw = f.read()
    if raw is None:
        import httpx
        resp = httpx.get(_CSV_URL, timeout=60.0)
        resp.raise_for_status()
        raw = resp.text
        with open(_CACHE, "w", encoding="utf-8") as f:
            f.write(raw)

    out: list[Match] = []
    for row in csv.DictReader(io.StringIO(raw)):
        try:
            hg = int(row["home_score"])
            ag = int(row["away_score"])
        except (ValueError, TypeError, KeyError):
            continue  # future fixtures (NA) and malformed rows
        try:
            d = datetime.strptime(row["date"], "%Y-%m-%d").date()
        except (ValueError, KeyError):
            continue
        home = (row.get("home_team") or "").strip().lower()
        away = (row.get("away_team") or "").strip().lower()
        if not home or not away:
            continue
        out.append(Match(
            d=d, home=home, away=away, hg=hg, ag=ag,
            friendly=_is_friendly(row.get("tournament", "")),
            neutral=(row.get("neutral", "").strip().upper() == "TRUE"),
        ))
    out.sort(key=lambda m: m.d)
    return out


# ---------------------------------------------------------------------- metrics
# (ordinal_rps / log_loss / brier / outcome_index are imported from backend.eval.scoring)

@dataclass
class Scorer:
    name: str
    n: int = 0
    rps: float = 0.0
    ll: float = 0.0
    bs: float = 0.0
    hits: int = 0
    # reliability bins for the predicted-winner probability
    bin_pred: list[float] = field(default_factory=lambda: [0.0] * 10)
    bin_obs: list[float] = field(default_factory=lambda: [0.0] * 10)
    bin_n: list[int] = field(default_factory=lambda: [0] * 10)

    def add(self, probs: tuple[float, float, float], obs: int) -> None:
        self.n += 1
        self.rps += ordinal_rps(probs, obs)
        self.ll += log_loss(probs, obs)
        self.bs += brier(probs, obs)
        pred = int(np.argmax(probs))
        if pred == obs:
            self.hits += 1
        # calibration on the max-probability call
        pmax = probs[pred]
        b = min(9, int(pmax * 10))
        self.bin_pred[b] += pmax
        self.bin_obs[b] += 1.0 if pred == obs else 0.0
        self.bin_n[b] += 1

    def row(self) -> str:
        if self.n == 0:
            return f"{self.name:<16} (no samples)"
        return (f"{self.name:<16} RPS={self.rps/self.n:.4f}  logloss={self.ll/self.n:.4f}  "
                f"Brier={self.bs/self.n:.4f}  acc={self.hits/self.n:.3f}  n={self.n}")

    def ece(self) -> float:
        """Expected calibration error on the predicted-winner probability."""
        if self.n == 0:
            return 0.0
        e = 0.0
        for b in range(10):
            if self.bin_n[b] == 0:
                continue
            conf = self.bin_pred[b] / self.bin_n[b]
            acc = self.bin_obs[b] / self.bin_n[b]
            e += (self.bin_n[b] / self.n) * abs(conf - acc)
        return e

    def reliability(self) -> str:
        lines = [f"  reliability ({self.name}, predicted-winner prob):"]
        for b in range(10):
            if self.bin_n[b] == 0:
                continue
            conf = self.bin_pred[b] / self.bin_n[b]
            acc = self.bin_obs[b] / self.bin_n[b]
            lines.append(f"    [{b/10:.1f}-{(b+1)/10:.1f})  conf={conf:.3f}  obs={acc:.3f}  n={self.bin_n[b]}")
        lines.append(f"    ECE={self.ece():.4f}")
        return "\n".join(lines)


# --------------------------------------------------------------- DC fit (reused)

def fit_dc(window: list[Match], cutoff: date, xi: float,
           comp_weight: float, min_matches: int) -> tuple[dict[str, float], dict[str, float]]:
    """Fit production DC params on `window`, weighting by time-decay to `cutoff`."""
    counts: dict[str, int] = {}
    for m in window:
        counts[m.home] = counts.get(m.home, 0) + 1
        counts[m.away] = counts.get(m.away, 0) + 1
    eligible = {t for t, c in counts.items() if c >= min_matches}
    rows = [m for m in window if m.home in eligible and m.away in eligible]
    if len(rows) < 100 or len(eligible) < 8:
        return {}, {}

    teams = sorted(eligible)
    tidx = {t: i for i, t in enumerate(teams)}
    n = len(teams)

    hi = np.array([tidx[m.home] for m in rows], dtype=np.int32)
    ai = np.array([tidx[m.away] for m in rows], dtype=np.int32)
    hg = np.array([m.hg for m in rows], dtype=np.float64)
    ag = np.array([m.ag for m in rows], dtype=np.float64)
    ws = np.array([
        math.exp(-xi * (cutoff - m.d).days) * (1.0 if m.friendly else comp_weight)
        for m in rows
    ], dtype=np.float64)

    params = _fit_sync(hi, ai, hg, ag, ws, n)
    la = {teams[i]: float(params[i]) for i in range(n)}
    ld = {teams[i]: float(params[n + i]) for i in range(n)}
    return la, ld


def dc_lambdas(la: dict, ld: dict, home: str, away: str) -> tuple[float, float] | None:
    if home not in la or away not in la:
        return None
    lh = math.exp(la[home] + ld[away])
    laa = math.exp(la[away] + ld[home])
    return max(LAMBDA_FLOOR, lh), max(LAMBDA_FLOOR, laa)


def probs_from_lambdas(lh: float, la: float, rho: float, max_goals: int,
                       temp: float = 1.0) -> tuple[float, float, float]:
    m = build_score_matrix(lh, la, max_goals=max_goals, rho=rho)
    p = match_probabilities(m)
    out = (p["home_win"], p["draw"], p["away_win"])
    if temp != 1.0:
        out = temperature_scale(out, temp)
    return out


def temperature_scale(probs: tuple[float, float, float], temp: float) -> tuple[float, float, float]:
    """Soften (temp>1) or sharpen (temp<1) a probability vector in log space."""
    logits = [math.log(max(1e-12, p)) / temp for p in probs]
    mx = max(logits)
    exps = [math.exp(x - mx) for x in logits]
    s = sum(exps)
    return (exps[0] / s, exps[1] / s, exps[2] / s)


# ------------------------------------------------------------------ Elo baseline

class Elo:
    """World-football-style Elo with goal-difference scaling and neutral handling."""

    def __init__(self, k: float = 40.0, home_adv: float = 65.0):
        self.k = k
        self.home_adv = home_adv
        self.r: dict[str, float] = {}

    def get(self, t: str) -> float:
        return self.r.get(t, 1500.0)

    def expected(self, home: str, away: str, neutral: bool) -> float:
        h = self.get(home) + (0.0 if neutral else self.home_adv)
        a = self.get(away)
        return 1.0 / (1.0 + 10.0 ** (-(h - a) / 400.0))

    def update(self, m: Match) -> None:
        we = self.expected(m.home, m.away, m.neutral)
        sh = 1.0 if m.hg > m.ag else (0.5 if m.hg == m.ag else 0.0)
        gd = abs(m.hg - m.ag)
        g = 1.0 if gd <= 1 else (1.5 if gd == 2 else (11 + gd) / 8.0)
        delta = self.k * g * (sh - we)
        self.r[m.home] = self.get(m.home) + delta
        self.r[m.away] = self.get(m.away) - delta


def elo_lambdas(we: float) -> tuple[float, float]:
    lh = max(LAMBDA_FLOOR, ELO_BASE_GOALS + ELO_SCALE * (we - 0.5))
    la = max(LAMBDA_FLOOR, ELO_BASE_GOALS - ELO_SCALE * (we - 0.5))
    return lh, la


# --------------------------------------------------------------------- backtest

def run(cutoffs: int, fit_years: int, step_months: int, xi: float, rho: float,
        comp_weight: float, min_matches: int, max_goals: int,
        do_xi_sweep: bool) -> None:
    print("Loading historical internationals ...")
    matches = load_matches()
    last = matches[-1].d
    print(f"  {len(matches)} completed matches, latest {last}")

    # Walk-forward cutoffs ending near the latest available real result.
    step = timedelta(days=step_months * 30)
    test_starts = [last - step * (i + 1) for i in range(cutoffs)][::-1]

    # Elo: one chronological pass; record PRE-match Elo win-expectation for every match.
    elo = Elo()
    elo_we: dict[int, float] = {}
    for idx, m in enumerate(matches):
        elo_we[idx] = elo.expected(m.home, m.away, m.neutral)
        elo.update(m)

    # Climatology baseline = base rates of [home, draw, away] on competitive matches.
    comp = [m for m in matches if not m.friendly]
    base = [0, 0, 0]
    for m in comp:
        base[outcome_index(m.hg, m.ag)] += 1
    clim = tuple(b / len(comp) for b in base)
    print(f"  climatology base rates  home={clim[0]:.3f} draw={clim[1]:.3f} away={clim[2]:.3f}")

    idx_by_match = {id(m): i for i, m in enumerate(matches)}

    # Collect test matches per cutoff with a single DC fit each.
    scorers = {
        "climatology": Scorer("climatology"),
        "elo": Scorer("elo"),
        "dc": Scorer("dc"),
        "blend-0.50": Scorer("blend-0.50"),
        "blend-0.65": Scorer("blend-0.65"),
        "blend-0.75": Scorer("blend-0.75"),
    }
    # store per-test-match data for post-hoc sweeps (rho, temp, blend-weight) without refit
    samples: list[dict] = []

    for ci, tstart in enumerate(test_starts):
        tend = tstart + step
        window = [m for m in matches if tstart - timedelta(days=fit_years * 365) <= m.d < tstart]
        test = [m for m in matches if tstart <= m.d < tend and not m.friendly]
        if not window or not test:
            continue
        print(f"\nCutoff {ci+1}/{len(test_starts)}: fit<{tstart}  test[{tstart}..{tend})  "
              f"window={len(window)} test={len(test)}  (fitting DC ...)")
        la, ld = fit_dc(window, tstart, xi, comp_weight, min_matches)
        if not la:
            print("  (insufficient data, skipped)")
            continue

        used = 0
        for m in test:
            dl = dc_lambdas(la, ld, m.home, m.away)
            mi = idx_by_match.get(id(m))
            we = elo_we.get(mi)
            if dl is None or we is None:
                continue
            obs = outcome_index(m.hg, m.ag)
            elh, ela = elo_lambdas(we)
            dlh, dla = dl

            p_clim = clim
            p_elo = probs_from_lambdas(elh, ela, rho, max_goals)
            p_dc = probs_from_lambdas(dlh, dla, rho, max_goals)
            scorers["climatology"].add(p_clim, obs)
            scorers["elo"].add(p_elo, obs)
            scorers["dc"].add(p_dc, obs)
            for w, key in ((0.50, "blend-0.50"), (0.65, "blend-0.65"), (0.75, "blend-0.75")):
                blh = w * dlh + (1 - w) * elh
                bla = w * dla + (1 - w) * ela
                scorers[key].add(probs_from_lambdas(blh, bla, rho, max_goals), obs)
            samples.append({"obs": obs, "tot": m.hg + m.ag,
                            "dlh": dlh, "dla": dla, "elh": elh, "ela": ela})
            used += 1
        print(f"  scored {used} test matches")

    if not samples:
        print("\nNo test samples scored — widen the window or lower --min-matches.")
        return

    print("\n" + "=" * 78)
    print(f"BACKTEST RESULTS  ({len(samples)} out-of-sample competitive matches)")
    print(f"config: xi={xi} rho={rho} fit_years={fit_years} comp_weight={comp_weight} "
          f"min_matches={min_matches} max_goals={max_goals}")
    print("=" * 78)
    order = ["climatology", "elo", "dc", "blend-0.50", "blend-0.65", "blend-0.75"]
    for k in order:
        print(scorers[k].row())
    print()
    print(scorers["dc"].reliability())
    print(scorers["blend-0.50"].reliability())

    # -------- post-hoc rho sweep (no refit) --------
    print("\n" + "-" * 78)
    print("RHO SWEEP on DC (no refit) — RPS / logloss:")
    for rr in (0.0, -0.05, -0.08, -0.13, -0.18):
        s = Scorer(f"rho={rr}")
        for smp in samples:
            s.add(probs_from_lambdas(smp["dlh"], smp["dla"], rr, max_goals), smp["obs"])
        print(f"  rho={rr:>6}: RPS={s.rps/s.n:.4f}  logloss={s.ll/s.n:.4f}  Brier={s.bs/s.n:.4f}")

    # -------- post-hoc blend-weight sweep (no refit) --------
    print("\n" + "-" * 78)
    print("DC/ELO BLEND-WEIGHT SWEEP (no refit) — w = DC weight — RPS / logloss / ECE:")
    for w in (0.0, 0.25, 0.40, 0.50, 0.60, 0.75, 0.90, 1.0):
        s = Scorer(f"w={w}")
        for smp in samples:
            blh = w * smp["dlh"] + (1 - w) * smp["elh"]
            bla = w * smp["dla"] + (1 - w) * smp["ela"]
            s.add(probs_from_lambdas(blh, bla, rho, max_goals), smp["obs"])
        print(f"  w={w:>4}: RPS={s.rps/s.n:.4f}  logloss={s.ll/s.n:.4f}  ECE={s.ece():.4f}")

    # -------- temperature calibration (fit on half, test on half) --------
    print("\n" + "-" * 78)
    print("TEMPERATURE CALIBRATION on DC (fit on 1st half, eval on 2nd half):")
    half = len(samples) // 2
    fit_s, test_s = samples[:half], samples[half:]

    def ll_at_temp(sset, temp):
        tot = 0.0
        for smp in sset:
            p = probs_from_lambdas(smp["dlh"], smp["dla"], rho, max_goals, temp=temp)
            tot += log_loss(p, smp["obs"])
        return tot / max(1, len(sset))

    best_t, best_ll = 1.0, float("inf")
    for t in [x / 20 for x in range(16, 45)]:  # 0.80 .. 2.20
        cur = ll_at_temp(fit_s, t)
        if cur < best_ll:
            best_ll, best_t = cur, t
    base_test = Scorer("dc raw (2nd half)")
    cal_test = Scorer(f"dc T={best_t} (2nd half)")
    for smp in test_s:
        base_test.add(probs_from_lambdas(smp["dlh"], smp["dla"], rho, max_goals), smp["obs"])
        cal_test.add(probs_from_lambdas(smp["dlh"], smp["dla"], rho, max_goals, temp=best_t), smp["obs"])
    print(f"  best temperature (in-sample): T={best_t}  (T>1 => model is over-confident)")
    print("  " + base_test.row())
    print("  " + cal_test.row())
    print(f"  ECE raw={base_test.ece():.4f}  ECE calibrated={cal_test.ece():.4f}")

    # -------- structural experiment: lambda-space blend vs supremacy/total decomposition --------
    # Fixed-sum ELO pins elo total to 2*BASE_GOALS. Lambda-space blend therefore drags the
    # blended total toward that constant. The "ST" variant takes TOTAL from DC and only blends
    # SUPREMACY from ELO, removing the pin. We score BOTH on 1X2 RPS and on Over/Under 2.5.
    def p_over25(lh: float, la: float) -> float:
        m = build_score_matrix(lh, la, max_goals=max_goals, rho=rho)
        over = 0.0
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                if i + j > 2:
                    over += float(m[i, j])
        return over

    def ou_brier_ll(prob_fn) -> tuple[float, float]:
        bs = ll = 0.0
        for smp in samples:
            po = prob_fn(smp)
            o = 1.0 if smp["tot"] > 2 else 0.0
            bs += (po - o) ** 2
            ll += -math.log(max(1e-12, po if o else 1 - po))
        n = len(samples)
        return bs / n, ll / n

    print("\n" + "-" * 78)
    print("STRUCTURAL: lambda-blend vs supremacy/total decomposition (fixes fixed-sum ELO)")
    print("  reporting 1X2 RPS  and  Over/Under 2.5 Brier / logloss")
    for w in (0.40, 0.50, 0.55):
        # lambda-space blend (current production style)
        s_l = Scorer(f"lam w={w}")
        def lam_lh(smp, w=w): return w * smp["dlh"] + (1 - w) * smp["elh"]
        def lam_la(smp, w=w): return w * smp["dla"] + (1 - w) * smp["ela"]
        for smp in samples:
            s_l.add(probs_from_lambdas(lam_lh(smp), lam_la(smp), rho, max_goals), smp["obs"])
        lb, ll_ = ou_brier_ll(lambda smp, w=w: p_over25(lam_lh(smp), lam_la(smp)))
        # supremacy/total: total from DC, supremacy blended
        s_st = Scorer(f"ST  w={w}")
        def st_lh(smp, w=w):
            T = smp["dlh"] + smp["dla"]; S = w * (smp["dlh"] - smp["dla"]) + (1 - w) * (smp["elh"] - smp["ela"])
            return max(LAMBDA_FLOOR, (T + S) / 2)
        def st_la(smp, w=w):
            T = smp["dlh"] + smp["dla"]; S = w * (smp["dlh"] - smp["dla"]) + (1 - w) * (smp["elh"] - smp["ela"])
            return max(LAMBDA_FLOOR, (T - S) / 2)
        for smp in samples:
            s_st.add(probs_from_lambdas(st_lh(smp), st_la(smp), rho, max_goals), smp["obs"])
        sb, sll = ou_brier_ll(lambda smp, w=w: p_over25(st_lh(smp), st_la(smp)))
        print(f"  lam w={w}: RPS={s_l.rps/s_l.n:.4f}  OU-Brier={lb:.4f}  OU-ll={ll_:.4f}")
        print(f"  ST  w={w}: RPS={s_st.rps/s_st.n:.4f}  OU-Brier={sb:.4f}  OU-ll={sll:.4f}")
    # OU climatology baseline
    over_rate = sum(1 for smp in samples if smp["tot"] > 2) / len(samples)
    ob = sum((over_rate - (1.0 if smp["tot"] > 2 else 0.0)) ** 2 for smp in samples) / len(samples)
    print(f"  OU climatology (base rate over={over_rate:.3f}): OU-Brier={ob:.4f}")

    if do_xi_sweep:
        print("\n" + "-" * 78)
        print("XI (time-decay) SWEEP — REFITS per cutoff, slow:")
        for xs in (0.0, 0.0015, PROD_XI, 0.006):
            s = Scorer(f"xi={xs}")
            for tstart in test_starts:
                tend = tstart + step
                window = [m for m in matches if tstart - timedelta(days=fit_years * 365) <= m.d < tstart]
                test = [m for m in matches if tstart <= m.d < tend and not m.friendly]
                if not window or not test:
                    continue
                la2, ld2 = fit_dc(window, tstart, xs, comp_weight, min_matches)
                if not la2:
                    continue
                for m in test:
                    dl = dc_lambdas(la2, ld2, m.home, m.away)
                    if dl is None:
                        continue
                    s.add(probs_from_lambdas(dl[0], dl[1], rho, max_goals), outcome_index(m.hg, m.ag))
            if s.n:
                print(f"  xi={xs:<8}: RPS={s.rps/s.n:.4f}  logloss={s.ll/s.n:.4f}  n={s.n}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Walk-forward backtest of the WC2026 goal model")
    ap.add_argument("--cutoffs", type=int, default=4)
    ap.add_argument("--fit-years", type=int, default=6)
    ap.add_argument("--step-months", type=int, default=6)
    ap.add_argument("--xi", type=float, default=PROD_XI)
    ap.add_argument("--rho", type=float, default=PROD_RHO)
    ap.add_argument("--comp-weight", type=float, default=PROD_COMP_WEIGHT)
    ap.add_argument("--min-matches", type=int, default=10)
    ap.add_argument("--max-goals", type=int, default=PROD_MAX_GOALS)
    ap.add_argument("--xi-sweep", action="store_true")
    args = ap.parse_args(argv)
    run(args.cutoffs, args.fit_years, args.step_months, args.xi, args.rho,
        args.comp_weight, args.min_matches, args.max_goals, args.xi_sweep)


if __name__ == "__main__":
    main(sys.argv[1:])
