from backend.models.elo_model import elo_to_lambdas
from backend.models.form import form_modifier


def test_equal_elo_gives_equal_lambdas():
    lh, la = elo_to_lambdas(1800, 1800)
    assert abs(lh - la) < 0.001


def test_higher_elo_gives_higher_lambda():
    lh, la = elo_to_lambdas(2000, 1600)
    assert lh > la


def test_lambdas_are_positive():
    lh, la = elo_to_lambdas(1200, 2100)
    assert lh > 0
    assert la > 0


def test_form_all_wins_positive():
    delta = form_modifier(["W", "W", "W", "W", "W"])
    assert delta > 0


def test_form_all_losses_negative():
    delta = form_modifier(["L", "L", "L", "L", "L"])
    assert delta < 0


def test_form_bounded():
    delta_max = form_modifier(["W", "W", "W", "W", "W"])
    delta_min = form_modifier(["L", "L", "L", "L", "L"])
    assert delta_max <= 0.10
    assert delta_min >= -0.10


def test_form_empty_returns_zero():
    assert form_modifier([]) == 0.0


def test_form_uses_last_five_only():
    long = ["L"] * 20 + ["W", "W", "W", "W", "W"]
    short = ["W", "W", "W", "W", "W"]
    assert abs(form_modifier(long) - form_modifier(short)) < 0.001
