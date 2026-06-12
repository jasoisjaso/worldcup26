from itertools import combinations


def optimize_accumulator(legs: list[dict], k: int) -> dict:
    if not legs or k < 1:
        return {"legs": [], "combined_odds": 1.0, "combined_prob": 0.0, "ev": 0.0}

    positive = [leg for leg in legs if leg["ev"] > 0]
    if len(positive) < k:
        return {"legs": [], "combined_odds": 1.0, "combined_prob": 0.0, "ev": 0.0}

    candidates = sorted(positive, key=lambda x: x["ev"], reverse=True)[:25]

    best_ev = float("-inf")
    best_combo: list[dict] = []
    best_odds = 1.0
    best_prob = 1.0

    for combo in combinations(candidates, k):
        combined_prob = 1.0
        combined_odds = 1.0
        for leg in combo:
            combined_prob *= leg["our_prob"]
            combined_odds *= leg["odds"]
        total_ev = (combined_prob * combined_odds) - 1.0
        if total_ev > best_ev:
            best_ev = total_ev
            best_combo = list(combo)
            best_odds = combined_odds
            best_prob = combined_prob

    return {
        "legs": best_combo,
        "combined_odds": round(best_odds, 2),
        "combined_prob": round(best_prob, 4),
        "ev": round(best_ev, 4),
    }
