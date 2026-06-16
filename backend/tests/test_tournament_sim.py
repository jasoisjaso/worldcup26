"""Tests for the tournament Monte Carlo (group stage).

The simulator is decoupled from the DB/async assembly: it takes a fixture list and a
per-match lambda map, so these tests are pure and fast (no network, no DB)."""
import math

from backend.models.tournament_sim import (
    SimMatch,
    rank_group,
    simulate_group_stage,
    simulate_tournament,
    load_bracket,
)


def _full_field():
    """12 groups A-L, 4 teams each, full round-robin — matches the official bracket labels."""
    matches, lambdas, elos = [], {}, {}
    for g in "ABCDEFGHIJKL":
        teams = [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]
        for t in teams:
            elos[t] = 1500.0
        matches.extend(_round_robin(g, teams))
    for m in matches:
        lambdas[m.id] = (1.3, 1.3)
    return matches, lambdas, elos


def _round_robin(group: str, teams: list[str]) -> list[SimMatch]:
    """6 matches for a 4-team group."""
    pairs = [(0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2)]
    return [
        SimMatch(id=f"{group}{i}", group=group, home=teams[h], away=teams[a])
        for i, (h, a) in enumerate(pairs)
    ]


def test_rank_group_basic_points_order():
    # A beats everyone, D loses everything -> A first, D last.
    codes = ["A", "B", "C", "D"]
    results = [
        ("A", "B", 2, 0), ("C", "D", 1, 0),
        ("A", "C", 1, 0), ("B", "D", 1, 0),
        ("A", "D", 3, 0), ("B", "C", 0, 0),
    ]
    import numpy as np
    order, stats = rank_group(codes, results, np.random.default_rng(1))
    assert order[0] == "A"
    assert order[-1] == "D"
    assert stats["A"]["pts"] == 9


def test_rank_group_head_to_head_breaks_tie():
    # B and C finish level on points, GD and GF; B beat C head-to-head -> B above C.
    # (B's H2H win over C is offset by C beating A while B lost to A, keeping totals equal.)
    codes = ["A", "B", "C", "D"]
    results = [
        ("A", "B", 1, 0),  # A beat B
        ("C", "A", 1, 0),  # C beat A
        ("B", "C", 1, 0),  # B beat C  <- decisive head-to-head
        ("B", "D", 1, 0),  # B beat D
        ("C", "D", 1, 0),  # C beat D
        ("D", "A", 1, 0),  # D beat A
    ]
    import numpy as np
    order, stats = rank_group(codes, results, np.random.default_rng(1))
    # B and C both have identical pts/gd/gf; head-to-head must put B above C.
    assert stats["B"]["pts"] == stats["C"]["pts"]
    assert stats["B"]["gd"] == stats["C"]["gd"]
    assert order.index("B") < order.index("C")


def test_simulate_group_probabilities_are_coherent():
    teams = ["t1", "t2", "t3", "t4"]
    matches = _round_robin("A", teams)
    # Equal lambdas -> roughly symmetric; just checking coherence.
    lambdas = {m.id: (1.3, 1.3) for m in matches}
    res = simulate_group_stage(matches, lambdas, n_sims=4000, seed=7)
    rows = res["teams"]
    assert len(rows) == 4
    for r in rows:
        for k in ("p_first", "p_second", "p_third", "p_top2", "p_advance"):
            assert 0.0 <= r[k] <= 1.0
    # Exactly one team finishes first per sim, and exactly two finish top-2.
    # (Structural invariants; tolerance absorbs 4-decimal display rounding.)
    assert math.isclose(sum(r["p_first"] for r in rows), 1.0, abs_tol=1e-3)
    assert math.isclose(sum(r["p_second"] for r in rows), 1.0, abs_tol=1e-3)
    assert math.isclose(sum(r["p_top2"] for r in rows), 2.0, abs_tol=1e-3)
    # p_advance >= p_top2 (advancing can also happen as a best third)
    for r in rows:
        assert r["p_advance"] >= r["p_top2"] - 1e-9


def test_stronger_team_advances_more_often():
    teams = ["strong", "mid1", "mid2", "weak"]
    matches = _round_robin("A", teams)
    lambdas = {}
    for m in matches:
        lh = 2.4 if m.home == "strong" else (0.6 if m.home == "weak" else 1.3)
        la = 2.4 if m.away == "strong" else (0.6 if m.away == "weak" else 1.3)
        lambdas[m.id] = (lh, la)
    res = simulate_group_stage(matches, lambdas, n_sims=4000, seed=3)
    by_code = {r["code"]: r for r in res["teams"]}
    assert by_code["strong"]["p_first"] > by_code["weak"]["p_first"]
    assert by_code["strong"]["p_advance"] > by_code["weak"]["p_advance"]


def test_completed_match_uses_actual_result():
    teams = ["t1", "t2", "t3", "t4"]
    matches = _round_robin("A", teams)
    # Force t1 to have thrashed everyone in completed games -> exp_points ~ 9.
    for m in matches:
        if m.home == "t1":
            m.status, m.home_score, m.away_score = "complete", 5, 0
        elif m.away == "t1":
            m.status, m.home_score, m.away_score = "complete", 0, 5
    lambdas = {m.id: (1.3, 1.3) for m in matches}
    res = simulate_group_stage(matches, lambdas, n_sims=2000, seed=1)
    by_code = {r["code"]: r for r in res["teams"]}
    # t1 won all three completed games -> always first, exp_points == 9.
    assert math.isclose(by_code["t1"]["p_first"], 1.0, abs_tol=1e-9)
    assert math.isclose(by_code["t1"]["exp_points"], 9.0, abs_tol=1e-9)


def test_determinism_same_seed():
    teams = ["t1", "t2", "t3", "t4"]
    matches = _round_robin("A", teams)
    lambdas = {m.id: (1.4, 1.1) for m in matches}
    a = simulate_group_stage(matches, lambdas, n_sims=2000, seed=42)
    b = simulate_group_stage(matches, lambdas, n_sims=2000, seed=42)
    assert a["teams"] == b["teams"]


def test_best_thirds_qualification_across_groups():
    # 4 groups, third-placed teams compete for 2 qualifying slots (mini world cup).
    all_matches = []
    lambdas = {}
    for g in ["A", "B", "C", "D"]:
        teams = [f"{g}1", f"{g}2", f"{g}3", f"{g}4"]
        ms = _round_robin(g, teams)
        all_matches.extend(ms)
        for m in ms:
            lambdas[m.id] = (1.3, 1.3)
    res = simulate_group_stage(all_matches, lambdas, n_sims=3000, seed=9, n_third_qualify=2)
    rows = res["teams"]
    # Exactly 2 thirds qualify per sim -> sum of p_third_qualify == 2.
    assert math.isclose(sum(r["p_third_qualify"] for r in rows), 2.0, abs_tol=1e-3)
    # 8 top-2 + 2 thirds = 10 advance per sim.
    assert math.isclose(sum(r["p_advance"] for r in rows), 10.0, abs_tol=1e-3)


def test_bracket_structure_is_intact():
    b = load_bracket()
    assert len(b["r32"]) == 16
    slots = [s for mm in b["r32"] for s in (mm["home"], mm["away"])]
    top2 = [s for s in slots if s[0] in "12"]
    assert len(top2) == 24 and len(set(top2)) == 24
    assert len(b["third_table"]) == 495
    assert {m["match"] for m in b["tree"]} == set(range(89, 105))


def test_tournament_round_invariants():
    matches, lambdas, elos = _full_field()
    res = simulate_tournament(matches, lambdas, elos, n_sims=2000, seed=11)
    rows = res["teams"]
    assert res["has_knockout"] is True
    assert len(rows) == 48
    # Structural: exactly one champion, two finalists, four semi-finalists, etc. per sim.
    assert math.isclose(sum(r["p_title"] for r in rows), 1.0, abs_tol=3e-3)
    assert math.isclose(sum(r["p_final"] for r in rows), 2.0, abs_tol=3e-3)
    assert math.isclose(sum(r["p_semi"] for r in rows), 4.0, abs_tol=3e-3)
    assert math.isclose(sum(r["p_quarter"] for r in rows), 8.0, abs_tol=3e-3)
    assert math.isclose(sum(r["p_r16"] for r in rows), 16.0, abs_tol=3e-3)
    assert math.isclose(sum(r["p_advance"] for r in rows), 32.0, abs_tol=3e-3)
    # Monotonic funnel: a team can't reach the final more often than the semis.
    for r in rows:
        assert r["p_advance"] >= r["p_r16"] - 1e-9 >= -1e-9
        assert r["p_semi"] >= r["p_final"] - 1e-9
        assert r["p_final"] >= r["p_title"] - 1e-9


def test_tournament_strong_team_wins_more():
    matches, lambdas, elos = _full_field()
    # Make A1 a juggernaut: huge elo + scores freely, concedes little.
    elos["A1"] = 2200.0
    for m in matches:
        if m.home == "A1":
            lambdas[m.id] = (3.2, 0.4)
        elif m.away == "A1":
            lambdas[m.id] = (0.4, 3.2)
    res = simulate_tournament(matches, lambdas, elos, n_sims=2000, seed=5)
    by = {r["code"]: r for r in res["teams"]}
    others = [r["p_title"] for c, r in by.items() if c != "A1"]
    assert by["A1"]["p_title"] > max(others)
    assert by["A1"]["p_advance"] > 0.95


def test_third_table_respects_official_slot_pools():
    from backend.models.tournament_sim import _THIRD_POOLS, _valid_row, match_thirds
    b = load_bracket()
    for key, asg in b["third_table"].items():
        assert _valid_row(asg), f"{key}: {asg} violates official slot pools"
        assert sorted(asg.values()) == sorted(key), f"{key}: not a bijection"
        assert set(asg.keys()) == set(_THIRD_POOLS), f"{key}: wrong slot set"
    # the matcher itself always yields a valid, complete matching
    for combo in ("ABCEGHKL", "ABCEGHIL", "EFGHIJKL", "ABCDEFGH"):
        m = match_thirds(combo)
        assert _valid_row(m) and sorted(m.values()) == sorted(combo)
