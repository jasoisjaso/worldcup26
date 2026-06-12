from datetime import datetime, timedelta


from backend.models.elo_model import elo_to_lambdas
from backend.models.form import form_modifier


def _dated(results: list[str], start_days_ago: int = 30) -> list[tuple[str, str]]:
    """Build dated tuples with results spaced 1 week apart, most recent = start_days_ago."""
    today = datetime.utcnow().date()
    dated = []
    for i, r in enumerate(results):
        d = today - timedelta(days=start_days_ago + i * 7)
        dated.append((d.strftime("%Y-%m-%d"), r))
    return list(reversed(dated))


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
    delta = form_modifier(_dated(["W", "W", "W", "W", "W"]))
    assert delta > 0


def test_form_all_losses_negative():
    delta = form_modifier(_dated(["L", "L", "L", "L", "L"]))
    assert delta < 0


def test_form_bounded():
    delta_max = form_modifier(_dated(["W", "W", "W", "W", "W"]))
    delta_min = form_modifier(_dated(["L", "L", "L", "L", "L"]))
    assert delta_max <= 0.10
    assert delta_min >= -0.10


def test_form_empty_returns_zero():
    assert form_modifier([]) == 0.0


def test_form_old_results_have_less_weight():
    # 20 losses 3 years ago followed by 5 recent wins: recent wins should dominate
    old_losses = _dated(["L"] * 20, start_days_ago=1000)
    recent_wins = _dated(["W"] * 5, start_days_ago=30)
    combined = old_losses + recent_wins
    recent_only = recent_wins
    # Both should be positive; combined may be lower due to old losses but still positive
    assert form_modifier(recent_only) > 0
    assert form_modifier(combined) > 0
