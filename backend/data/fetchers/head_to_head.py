"""
Head-to-head record multiplier from martj42 competitive results.

Uses the _raw_matches store built by results.py (shared download).
Covers all competitive international matches — no friendlies.

Effect is intentionally small (±4% max) — H2H is a secondary signal,
not a primary predictor. Meaningful for historically one-sided matchups
(Brazil vs Morocco, Argentina vs Algeria) where 10+ years of data exist.
"""
from __future__ import annotations


async def get_h2h_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    from backend.data.fetchers.results import _raw_matches, refresh_form_cache

    if not _raw_matches:
        await refresh_form_cache()

    hw = d = aw = 0
    for r in _raw_matches:
        if r["home"] == home_code and r["away"] == away_code:
            if r["hg"] > r["ag"]:
                hw += 1
            elif r["hg"] == r["ag"]:
                d += 1
            else:
                aw += 1
        elif r["home"] == away_code and r["away"] == home_code:
            if r["hg"] > r["ag"]:
                aw += 1
            elif r["hg"] == r["ag"]:
                d += 1
            else:
                hw += 1

    total = hw + d + aw
    if total < 4:
        return 1.0, 1.0   # not enough competitive history to be meaningful

    home_rate = (hw + 0.5 * d) / total
    # Centre at 0.5 → max ±4% when one team dominates completely
    adj = max(-0.04, min(0.04, (home_rate - 0.5) * 0.08))
    return round(1.0 + adj, 4), round(1.0 - adj, 4)
