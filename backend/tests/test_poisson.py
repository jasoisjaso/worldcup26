import pytest
from backend.models.poisson import (
    build_score_matrix,
    match_probabilities,
    over_under_probability,
    btts_probability,
    top_scores,
)


def test_score_matrix_sums_to_one():
    matrix = build_score_matrix(1.5, 1.2)
    assert abs(matrix.sum() - 1.0) < 0.01


def test_match_probabilities_sum_to_one():
    matrix = build_score_matrix(1.5, 1.2)
    probs = match_probabilities(matrix)
    total = probs["home_win"] + probs["draw"] + probs["away_win"]
    assert abs(total - 1.0) < 0.001


def test_strong_team_wins_more():
    matrix = build_score_matrix(2.5, 0.5)
    probs = match_probabilities(matrix)
    assert probs["home_win"] > 0.8


def test_over_under_sums_to_one():
    matrix = build_score_matrix(1.5, 1.2)
    result = over_under_probability(matrix, line=2.5)
    assert abs(result["over"] + result["under"] - 1.0) < 0.001


def test_btts_range():
    matrix = build_score_matrix(1.5, 1.2)
    p = btts_probability(matrix)
    assert 0.0 <= p <= 1.0


def test_top_scores_length():
    matrix = build_score_matrix(1.5, 1.2)
    scores = top_scores(matrix, n=6)
    assert len(scores) == 6


def test_top_scores_sorted_descending():
    matrix = build_score_matrix(1.5, 1.2)
    scores = top_scores(matrix, n=6)
    probs = [s["probability"] for s in scores]
    assert probs == sorted(probs, reverse=True)
