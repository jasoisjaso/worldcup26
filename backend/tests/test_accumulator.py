from backend.betting.accumulator import optimize_accumulator


LEGS = [
    {"match_id": "M1", "market": "home_win", "our_prob": 0.65, "odds": 1.80, "ev": 0.17},
    {"match_id": "M2", "market": "away_win", "our_prob": 0.55, "odds": 2.10, "ev": 0.155},
    {"match_id": "M3", "market": "over_2_5", "our_prob": 0.62, "odds": 1.90, "ev": 0.178},
    {"match_id": "M4", "market": "home_win", "our_prob": 0.72, "odds": 1.70, "ev": 0.224},
    {"match_id": "M5", "market": "draw",     "our_prob": 0.35, "odds": 3.20, "ev": 0.12},
]


def test_returns_correct_leg_count():
    result = optimize_accumulator(LEGS, k=3)
    assert len(result["legs"]) == 3


def test_combined_odds_calculated():
    result = optimize_accumulator(LEGS, k=3)
    assert result["combined_odds"] > 1.0


def test_combined_prob_is_product():
    result = optimize_accumulator(LEGS, k=3)
    prod = 1.0
    for leg in result["legs"]:
        prod *= leg["our_prob"]
    assert abs(result["combined_prob"] - prod) < 0.001


def test_only_positive_ev_legs_included():
    mixed = LEGS + [
        {"match_id": "M6", "market": "home_win", "our_prob": 0.30, "odds": 1.50, "ev": -0.10},
    ]
    result = optimize_accumulator(mixed, k=3)
    for leg in result["legs"]:
        assert leg["ev"] > 0


def test_empty_returns_empty():
    result = optimize_accumulator([], k=3)
    assert result["legs"] == []
