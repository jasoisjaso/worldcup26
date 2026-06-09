import numpy as np
from scipy.stats import poisson


def build_score_matrix(lambda_home: float, lambda_away: float, max_goals: int = 8) -> np.ndarray:
    home_probs = poisson.pmf(np.arange(max_goals + 1), lambda_home)
    away_probs = poisson.pmf(np.arange(max_goals + 1), lambda_away)
    return np.outer(home_probs, away_probs)


def match_probabilities(matrix: np.ndarray) -> dict[str, float]:
    home_win = float(np.sum(np.tril(matrix, -1)))
    draw = float(np.sum(np.diag(matrix)))
    away_win = float(np.sum(np.triu(matrix, 1)))
    return {"home_win": home_win, "draw": draw, "away_win": away_win}


def over_under_probability(matrix: np.ndarray, line: float = 2.5) -> dict[str, float]:
    rows, cols = matrix.shape
    total_goals = np.array([[i + j for j in range(cols)] for i in range(rows)])
    over = float(np.sum(matrix[total_goals > line]))
    under = float(np.sum(matrix[total_goals <= line]))
    return {"over": over, "under": under}


def btts_probability(matrix: np.ndarray) -> float:
    p_home_scoreless = float(np.sum(matrix[0, :]))
    p_away_scoreless = float(np.sum(matrix[:, 0]))
    p_both_scoreless = float(matrix[0, 0])
    return 1.0 - p_home_scoreless - p_away_scoreless + p_both_scoreless


def top_scores(matrix: np.ndarray, n: int = 6) -> list[dict]:
    rows, cols = matrix.shape
    scores = [
        {"home": i, "away": j, "probability": float(matrix[i, j])}
        for i in range(rows)
        for j in range(cols)
    ]
    return sorted(scores, key=lambda x: x["probability"], reverse=True)[:n]


def asian_handicap_probability(matrix: np.ndarray, line: float) -> dict[str, float]:
    rows, cols = matrix.shape
    home_covers = 0.0
    away_covers = 0.0
    push = 0.0

    for i in range(rows):
        for j in range(cols):
            margin = i - j
            adjusted = margin + line
            p = float(matrix[i, j])
            if adjusted > 0:
                home_covers += p
            elif adjusted < 0:
                away_covers += p
            else:
                push += p

    home_covers += push / 2
    away_covers += push / 2
    return {"home_covers": home_covers, "away_covers": away_covers}
