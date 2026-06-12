"""Network-free guardrail for the offline backtest engine.

Builds a synthetic league with a known strength gradient, fits the *production* DC code
via the harness, and asserts the model beats a climatology baseline out-of-sample. This
keeps the validation gate honest without depending on the live martj42 download.
"""
import random

from backend.eval.backtest import (
    Match, fit_dc, dc_lambdas, probs_from_lambdas, Scorer, PROD_RHO,
)
from backend.eval.scoring import outcome_index
from datetime import date, timedelta


def _synthetic_matches(n_teams=10, n_rounds=26, seed=7):
    rng = random.Random(seed)
    teams = [f"t{i}" for i in range(n_teams)]
    # strength 0..1; stronger teams have higher scoring rate
    strength = {t: i / (n_teams - 1) for i, t in enumerate(teams)}
    start = date(2020, 1, 1)
    matches = []
    d = start
    for _ in range(n_rounds):
        rng.shuffle(teams)
        for a, b in zip(teams[::2], teams[1::2]):
            la = 0.6 + 1.8 * strength[a]
            lb = 0.6 + 1.8 * strength[b]
            hg = min(6, sum(1 for _ in range(8) if rng.random() < la / 8))
            ag = min(6, sum(1 for _ in range(8) if rng.random() < lb / 8))
            matches.append(Match(d=d, home=a, away=b, hg=hg, ag=ag,
                                 friendly=False, neutral=True))
            d = d + timedelta(days=1)
    return matches, strength


def test_fit_recovers_strength_ordering():
    matches, strength = _synthetic_matches()
    cutoff = matches[-1].d + timedelta(days=1)
    la, ld = fit_dc(matches, cutoff, xi=0.0, comp_weight=1.0, min_matches=4)
    assert la, "fit returned no params"
    weakest = min(strength, key=strength.get)
    strongest = max(strength, key=strength.get)
    # stronger team should have the larger fitted attack parameter
    assert la[strongest] > la[weakest]


def test_strong_beats_weak_in_probs():
    matches, strength = _synthetic_matches()
    cutoff = matches[-1].d + timedelta(days=1)
    la, ld = fit_dc(matches, cutoff, xi=0.0, comp_weight=1.0, min_matches=4)
    strongest = max(strength, key=strength.get)
    weakest = min(strength, key=strength.get)
    lam = dc_lambdas(la, ld, strongest, weakest)
    assert lam is not None
    p = probs_from_lambdas(lam[0], lam[1], PROD_RHO, 8)
    assert p[0] > p[2]  # home (strong) more likely than away (weak)


def test_model_beats_climatology_out_of_sample():
    matches, _ = _synthetic_matches(n_rounds=40)
    split = int(len(matches) * 0.7)
    train, test = matches[:split], matches[split:]
    cutoff = train[-1].d + timedelta(days=1)
    la, ld = fit_dc(train, cutoff, xi=0.0, comp_weight=1.0, min_matches=4)
    assert la

    base = [0, 0, 0]
    for m in train:
        base[outcome_index(m.hg, m.ag)] += 1
    clim = tuple(b / len(train) for b in base)

    model_s, clim_s = Scorer("dc"), Scorer("clim")
    for m in test:
        lam = dc_lambdas(la, ld, m.home, m.away)
        if lam is None:
            continue
        obs = outcome_index(m.hg, m.ag)
        model_s.add(probs_from_lambdas(lam[0], lam[1], PROD_RHO, 8), obs)
        clim_s.add(clim, obs)

    assert model_s.n > 0
    assert model_s.rps / model_s.n < clim_s.rps / clim_s.n
