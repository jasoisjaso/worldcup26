"""Derived betting-markets sheet.

The match model produces one Dixon-Coles home-goals x away-goals score matrix. From that
single matrix (plus a half-time split) we can price ~30 markets beyond 1X2 / Over-Under —
double chance, draw-no-bet, team totals, clean sheet, win-to-nil, exact goals, odd/even,
an Asian-handicap ladder, half-time and HT/FT. We publish the model's FAIR ODDS (1 / prob)
for every one, so a punter can line-shop their own bookmaker: any price longer than our
fair odds is, by the model, value. Everything derives from the same matrix, so the whole
sheet is internally consistent with the headline numbers.

Half-time model: first-half goals are an independent Poisson with lambda = HT_FACTOR * the
full-time lambda (~45/55 split — more goals come after the break); the second half gets the
remainder. HT/FT is the joint over the two independent halves. Plain Poisson (no rho) for
the halves — the low-score correction is negligible split across 45 minutes.
"""
from __future__ import annotations

import numpy as np

from backend.models.poisson import (
    asian_handicap_probability,
    build_score_matrix,
    match_probabilities,
)

HT_FACTOR = 0.45  # share of full-time goal expectation that lands in the first half


def _fair(p: float) -> float | None:
    """Fair decimal odds for a probability. None for vanishingly small probabilities."""
    if p <= 1e-4:
        return None
    return round(1.0 / p, 2)


def _o(key: str, label: str, prob: float) -> dict:
    prob = max(0.0, min(1.0, float(prob)))
    return {"key": key, "label": label, "prob": round(prob, 4), "fair_odds": _fair(prob)}


def _result_index_probs(matrix: np.ndarray) -> tuple[float, float, float]:
    mp = match_probabilities(matrix)
    return mp["home_win"], mp["draw"], mp["away_win"]


def _totals(matrix: np.ndarray) -> dict[float, float]:
    """P(total goals > line) for each half-line."""
    rows, cols = matrix.shape
    totals = np.add.outer(np.arange(rows), np.arange(cols))
    out = {}
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        out[line] = float(matrix[totals > line].sum())
    return out


def _exact_goals(matrix: np.ndarray, cap: int = 6) -> list[float]:
    """P(total goals == n) for n in 0..cap-1, and >= cap as the last bucket."""
    rows, cols = matrix.shape
    totals = np.add.outer(np.arange(rows), np.arange(cols))
    probs = [float(matrix[totals == n].sum()) for n in range(cap)]
    probs.append(float(matrix[totals >= cap].sum()))
    return probs


def derive_markets(lambda_home: float, lambda_away: float, rho: float = -0.13,
                   max_goals: int = 10) -> dict:
    # 10 goals/team (not the headline 8) so the right tail of totals / exact-goals stays
    # accurate even for high-scoring matchups; 1X2-derived markets are unaffected.
    m = build_score_matrix(lambda_home, lambda_away, max_goals=max_goals, rho=rho)
    rows, cols = m.shape
    h, d, a = _result_index_probs(m)

    groups: list[dict] = []

    # --- result + derivatives -------------------------------------------------------
    groups.append({"key": "result", "name": "Match result", "outcomes": [
        _o("home_win", "Home win", h), _o("draw", "Draw", d), _o("away_win", "Away win", a),
    ]})
    groups.append({"key": "double_chance", "name": "Double chance", "outcomes": [
        _o("1X", "Home or draw", h + d), _o("12", "Home or away", h + a), _o("X2", "Draw or away", d + a),
    ]})
    nodraw = h + a
    groups.append({"key": "draw_no_bet", "name": "Draw no bet", "outcomes": [
        _o("home", "Home (DNB)", h / nodraw if nodraw else 0.0),
        _o("away", "Away (DNB)", a / nodraw if nodraw else 0.0),
    ]})

    # --- totals ---------------------------------------------------------------------
    tot = _totals(m)
    tot_out = []
    for line in (0.5, 1.5, 2.5, 3.5, 4.5):
        tag = str(line).replace(".", "_")
        tot_out.append(_o(f"over_{tag}", f"Over {line}", tot[line]))
        tot_out.append(_o(f"under_{tag}", f"Under {line}", 1.0 - tot[line]))
    groups.append({"key": "totals", "name": "Total goals", "outcomes": tot_out})

    # odd/even total
    totals_grid = np.add.outer(np.arange(rows), np.arange(cols))
    p_even = float(m[totals_grid % 2 == 0].sum())
    groups.append({"key": "odd_even", "name": "Odd / even goals", "outcomes": [
        _o("odd", "Odd", 1.0 - p_even), _o("even", "Even", p_even),
    ]})

    # exact total goals
    eg = _exact_goals(m, cap=6)
    eg_out = [_o(f"goals_{n}", f"{n} goals", eg[n]) for n in range(6)]
    eg_out.append(_o("goals_6plus", "6+ goals", eg[6]))
    groups.append({"key": "exact_goals", "name": "Exact total goals", "outcomes": eg_out})

    # --- both teams to score --------------------------------------------------------
    p_home_blank = float(m[0, :].sum())   # home scores 0
    p_away_blank = float(m[:, 0].sum())   # away scores 0
    p_btts = 1.0 - p_home_blank - p_away_blank + float(m[0, 0])
    groups.append({"key": "btts", "name": "Both teams to score", "outcomes": [
        _o("yes", "Yes", p_btts), _o("no", "No", 1.0 - p_btts),
    ]})

    # --- team totals ----------------------------------------------------------------
    home_goal_probs = m.sum(axis=1)  # marginal of home goals
    away_goal_probs = m.sum(axis=0)
    tt_out = []
    for side, marg in (("home", home_goal_probs), ("away", away_goal_probs)):
        label = "Home" if side == "home" else "Away"
        for line, idx in ((0.5, 1), (1.5, 2), (2.5, 3)):
            tag = str(line).replace(".", "_")
            p_over = float(marg[idx:].sum())
            tt_out.append(_o(f"{side}_over_{tag}", f"{label} over {line}", p_over))
    groups.append({"key": "team_totals", "name": "Team totals", "outcomes": tt_out})

    # --- clean sheet / win to nil ---------------------------------------------------
    groups.append({"key": "clean_sheet", "name": "Clean sheet", "outcomes": [
        _o("home", "Home clean sheet", p_away_blank), _o("away", "Away clean sheet", p_home_blank),
    ]})
    # win to nil: win AND concede zero
    home_wtn = float(np.tril(m, -1)[:, 0].sum())  # home>away and away==0 -> column 0, home>0
    away_wtn = float(np.triu(m, 1)[0, :].sum())   # away>home and home==0 -> row 0
    groups.append({"key": "win_to_nil", "name": "Win to nil", "outcomes": [
        _o("home", "Home win to nil", home_wtn), _o("away", "Away win to nil", away_wtn),
    ]})

    # --- asian handicap ladder (home covers) ----------------------------------------
    ah_out = []
    for line in (-2.5, -1.5, -0.5, 0.5, 1.5, 2.5):
        cover = asian_handicap_probability(m, line=line)["home_covers"]
        tag = str(line).replace(".", "_")
        sign = f"{line:+.1f}".replace(".0", "")
        ah_out.append(_o(f"home_{tag}", f"Home {sign}", cover))
    groups.append({"key": "asian_handicap", "name": "Asian handicap (home)", "outcomes": ah_out})

    # --- correct score (top 8) ------------------------------------------------------
    flat = [(i, j, float(m[i, j])) for i in range(rows) for j in range(cols)]
    flat.sort(key=lambda x: x[2], reverse=True)
    cs_out = [_o(f"cs_{i}_{j}", f"{i}-{j}", p) for i, j, p in flat[:8]]
    groups.append({"key": "correct_score", "name": "Correct score (top 8)", "outcomes": cs_out})

    # --- half-time model ------------------------------------------------------------
    lh1, la1 = lambda_home * HT_FACTOR, lambda_away * HT_FACTOR
    lh2, la2 = lambda_home - lh1, lambda_away - la1
    m1 = build_score_matrix(lh1, la1, max_goals=max_goals, rho=0.0)
    m2 = build_score_matrix(lh2, la2, max_goals=max_goals, rho=0.0)
    h1, d1, a1 = _result_index_probs(m1)
    groups.append({"key": "ht_result", "name": "Half-time result", "outcomes": [
        _o("home_win", "Home", h1), _o("draw", "Draw", d1), _o("away_win", "Away", a1),
    ]})
    ht_tot = _totals(m1)
    groups.append({"key": "ht_totals", "name": "Half-time goals", "outcomes": [
        _o("over_0_5", "Over 0.5", ht_tot[0.5]), _o("under_0_5", "Under 0.5", 1.0 - ht_tot[0.5]),
        _o("over_1_5", "Over 1.5", ht_tot[1.5]), _o("under_1_5", "Under 1.5", 1.0 - ht_tot[1.5]),
    ]})

    # HT/FT: joint over two independent halves
    def _sign(diff: int) -> str:
        return "H" if diff > 0 else ("D" if diff == 0 else "A")

    r1, c1 = m1.shape
    r2, c2 = m2.shape
    htft = {f"{x}{y}": 0.0 for x in "HDA" for y in "HDA"}
    for i1 in range(r1):
        for j1 in range(c1):
            p1 = m1[i1, j1]
            if p1 < 1e-9:
                continue
            ht = _sign(i1 - j1)
            for i2 in range(r2):
                row2 = m2[i2]
                for j2 in range(c2):
                    p2 = row2[j2]
                    if p2 < 1e-9:
                        continue
                    ft = _sign((i1 + i2) - (j1 + j2))
                    htft[f"{ht}{ft}"] += float(p1 * p2)
    _name = {"H": "Home", "D": "Draw", "A": "Away"}
    htft_out = [_o(f"{x}{y}", f"{_name[x]}/{_name[y]}", htft[f"{x}{y}"]) for x in "HDA" for y in "HDA"]
    groups.append({"key": "htft", "name": "Half-time / full-time", "outcomes": htft_out})

    # Score-line heatmap grid: P(home=i, away=j) for 0..6 each. The signature visualisation
    # (a Dixon-Coles shot-map-style heatmap). grid[i][j], plus the peak cell for scaling.
    gmax = 6
    grid = [[round(float(m[i, j]), 4) for j in range(gmax + 1)] for i in range(gmax + 1)]
    peak = max(max(row) for row in grid)

    return {
        "lambda_home": round(lambda_home, 3),
        "lambda_away": round(lambda_away, 3),
        "expected_total": round(lambda_home + lambda_away, 2),
        "score_grid": {"grid": grid, "max": gmax, "peak": peak},
        "groups": groups,
    }
