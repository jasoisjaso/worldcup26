import math
from datetime import datetime

_XI = 0.00325  # exp decay per day; validated on 5-season club data (dashee87/Dixon-Coles)


def form_modifier(results: list[tuple[str, str]]) -> float:
    """
    Time-decayed form modifier from dated results.
    results: list of ("YYYY-MM-DD", "W"/"D"/"L"), oldest first.
    Returns lambda delta clamped to [-0.10, +0.10].
    """
    if not results:
        return 0.0
    today = datetime.utcnow().date()
    points = {"W": 1.0, "D": 0.0, "L": -1.0}
    weighted_sum = 0.0
    weight_total = 0.0
    for date_str, result in results:
        try:
            match_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue
        days_ago = max(0, (today - match_date).days)
        w = math.exp(-_XI * days_ago)
        weighted_sum += w * points.get(result, 0.0)
        weight_total += w
    if weight_total == 0:
        return 0.0
    raw = weighted_sum / weight_total  # weighted average in [-1.0, 1.0]
    return round(max(-0.10, min(0.10, raw * 0.10)), 4)
