"""Unit tests for dc_ratings.get_lambdas — no network, manually inject params."""
import math
import backend.models.dc_ratings as dc


def _inject(log_attack: dict, log_defense: dict) -> None:
    dc._log_attack = log_attack
    dc._log_defense = log_defense
    dc._built_at = None  # don't mark as fresh — we're bypassing ensure_fitted


def _reset() -> None:
    dc._log_attack = {}
    dc._log_defense = {}
    dc._built_at = None


def test_get_lambdas_returns_none_when_no_params():
    _reset()
    assert dc.get_lambdas("fr", "de") is None


def test_get_lambdas_returns_none_when_one_team_missing():
    _inject({"fr": 0.3}, {"fr": -0.2})
    assert dc.get_lambdas("fr", "de") is None
    _reset()


def test_get_lambdas_symmetric_equal_teams():
    """Equal attack/defense → equal lambdas."""
    _inject({"fr": 0.0, "de": 0.0}, {"fr": 0.0, "de": 0.0})
    lh, la = dc.get_lambdas("fr", "de")
    assert abs(lh - la) < 1e-9
    _reset()


def test_get_lambdas_stronger_attack_raises_own_lambda():
    """Higher log_attack for home team → higher home lambda."""
    _inject({"fr": 0.5, "de": 0.0}, {"fr": 0.0, "de": 0.0})
    lh, la = dc.get_lambdas("fr", "de")
    assert lh > la
    _reset()


def test_get_lambdas_stronger_defense_lowers_opponent_lambda():
    """Better (lower) log_defense for away team → lower home lambda."""
    _inject({"fr": 0.0, "de": 0.0}, {"fr": 0.0, "de": -0.5})
    lh, la = dc.get_lambdas("fr", "de")
    assert lh < la
    _reset()


def test_get_lambdas_floor_applied():
    """Even a very weak team gets at least 0.3 expected goals."""
    _inject({"fr": 2.0, "de": -2.0}, {"fr": 2.0, "de": -2.0})
    lh, la = dc.get_lambdas("fr", "de")
    assert lh >= 0.3
    assert la >= 0.3
    _reset()


def test_get_lambdas_math_correct():
    """Spot-check: λ = exp(log_α_home + log_β_away)."""
    _inject({"fr": 0.2, "de": -0.1}, {"fr": -0.15, "de": 0.1})
    lh, la = dc.get_lambdas("fr", "de")
    expected_lh = math.exp(0.2 + 0.1)   # log_α_fr + log_β_de
    expected_la = math.exp(-0.1 + -0.15)  # log_α_de + log_β_fr
    assert abs(lh - expected_lh) < 1e-9
    assert abs(la - expected_la) < 1e-9
    _reset()
