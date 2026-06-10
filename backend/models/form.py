def form_modifier(results: list[str]) -> float:
    """Given W/D/L results (oldest first), return lambda delta in range -0.3 to +0.3."""
    if not results:
        return 0.0
    recent = results[-5:]
    weights = [0.1, 0.15, 0.2, 0.25, 0.3][-len(recent):]
    points = {"W": 1.0, "D": 0.0, "L": -1.0}
    weighted = sum(w * points[r] for w, r in zip(weights, recent))
    return round(max(-0.10, min(0.10, weighted)), 4)
