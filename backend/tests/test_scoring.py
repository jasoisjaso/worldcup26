import math

from backend.eval.scoring import (
    outcome_index, ordinal_rps, log_loss, brier,
    binary_brier, binary_log_loss, reliability_table, expected_calibration_error,
)


def test_outcome_index():
    assert outcome_index(2, 0) == 0
    assert outcome_index(1, 1) == 1
    assert outcome_index(0, 3) == 2


def test_ordinal_rps_perfect_and_worst():
    assert ordinal_rps((1.0, 0.0, 0.0), 0) == 0.0
    # certain away, home happens -> max ordinal error
    assert math.isclose(ordinal_rps((0.0, 0.0, 1.0), 0), 1.0, abs_tol=1e-9)


def test_ordinal_rps_rewards_adjacent_miss_over_distant():
    # predicting draw, actual home (adjacent) should beat predicting away, actual home
    adjacent = ordinal_rps((0.0, 1.0, 0.0), 0)
    distant = ordinal_rps((0.0, 0.0, 1.0), 0)
    assert adjacent < distant


def test_log_loss_and_brier():
    assert math.isclose(brier((1.0, 0.0, 0.0), 0), 0.0, abs_tol=1e-9)
    assert log_loss((0.5, 0.25, 0.25), 0) > 0


def test_binary_scores():
    assert math.isclose(binary_brier(0.7, True), 0.09, abs_tol=1e-9)
    assert binary_log_loss(1.0, True) >= 0  # clamped, no inf
    assert binary_log_loss(0.0, True) > 10  # confidently wrong is heavily penalised


def test_reliability_and_ece():
    pairs = [(0.9, True), (0.9, True), (0.1, False), (0.1, False)]
    table = reliability_table(pairs)
    assert all(row["confidence"] >= 0 and row["frequency"] >= 0 for row in table)
    # perfectly calibrated -> ECE ~ 0
    assert expected_calibration_error(pairs) < 0.11
