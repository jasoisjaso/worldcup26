"""Tests for the derived betting-markets sheet.

Every market is derived from the same Dixon-Coles score matrix as the headline 1X2/O-U
numbers, so the fair odds across the board stay internally consistent."""
import math

from backend.betting.markets import derive_markets


def _group(sheet, key):
    return next(g for g in sheet["groups"] if g["key"] == key)


def _by(group, key):
    return next(o for o in group["outcomes"] if o["key"] == key)


def test_result_matches_and_fair_odds_are_inverse_probability():
    s = derive_markets(1.6, 1.0)
    res = _group(s, "result")
    p = {o["key"]: o["prob"] for o in res["outcomes"]}
    assert math.isclose(p["home_win"] + p["draw"] + p["away_win"], 1.0, abs_tol=1e-6)
    # stronger home team favoured
    assert p["home_win"] > p["away_win"]
    # fair odds == 1 / prob
    for o in res["outcomes"]:
        assert math.isclose(o["fair_odds"], round(1.0 / o["prob"], 2), abs_tol=0.01)


def test_double_chance_and_dnb_are_coherent():
    s = derive_markets(1.4, 1.2)
    res = {o["key"]: o["prob"] for o in _group(s, "result")["outcomes"]}
    dc = {o["key"]: o["prob"] for o in _group(s, "double_chance")["outcomes"]}
    assert math.isclose(dc["1X"], res["home_win"] + res["draw"], abs_tol=1e-6)
    assert math.isclose(dc["12"], res["home_win"] + res["away_win"], abs_tol=1e-6)
    assert math.isclose(dc["X2"], res["draw"] + res["away_win"], abs_tol=1e-6)
    dnb = {o["key"]: o["prob"] for o in _group(s, "draw_no_bet")["outcomes"]}
    assert math.isclose(dnb["home"] + dnb["away"], 1.0, abs_tol=1e-6)


def test_totals_each_line_sums_to_one():
    s = derive_markets(1.5, 1.5)
    totals = _group(s, "totals")
    # group by line: over_X + under_X == 1
    overs = {o["key"]: o["prob"] for o in totals["outcomes"] if o["key"].startswith("over_")}
    unders = {o["key"]: o["prob"] for o in totals["outcomes"] if o["key"].startswith("under_")}
    for line in ("0_5", "1_5", "2_5", "3_5"):
        assert math.isclose(overs[f"over_{line}"] + unders[f"under_{line}"], 1.0, abs_tol=1e-6)
    # monotone: harder to go over a higher line
    assert overs["over_0_5"] > overs["over_1_5"] > overs["over_2_5"] > overs["over_3_5"]


def test_team_totals_and_clean_sheet_and_win_to_nil():
    s = derive_markets(2.0, 0.5)  # home strong, away weak
    tt = {o["key"]: o["prob"] for o in _group(s, "team_totals")["outcomes"]}
    assert 0 < tt["home_over_1_5"] < 1
    # weak away less likely to score 2+ than strong home
    assert tt["home_over_1_5"] > tt["away_over_1_5"]
    cs = {o["key"]: o["prob"] for o in _group(s, "clean_sheet")["outcomes"]}
    # strong home keeps a clean sheet more often than weak away
    assert cs["home"] > cs["away"]
    wtn = {o["key"]: o["prob"] for o in _group(s, "win_to_nil")["outcomes"]}
    assert 0 <= wtn["home"] <= 1


def test_exact_goals_and_odd_even_partition_probability():
    s = derive_markets(1.3, 1.1)
    eg = _group(s, "exact_goals")
    assert math.isclose(sum(o["prob"] for o in eg["outcomes"]), 1.0, abs_tol=1e-6)
    oe = {o["key"]: o["prob"] for o in _group(s, "odd_even")["outcomes"]}
    assert math.isclose(oe["odd"] + oe["even"], 1.0, abs_tol=1e-6)


def test_halftime_fulltime_partition():
    s = derive_markets(1.6, 1.1)
    htft = _group(s, "htft")
    assert len(htft["outcomes"]) == 9
    # raw joint sums to exactly 1 (product of two normalised half-matrices); tolerance
    # absorbs 4-decimal display rounding across the 9 cells.
    assert math.isclose(sum(o["prob"] for o in htft["outcomes"]), 1.0, abs_tol=2e-3)
    ht = {o["key"]: o["prob"] for o in _group(s, "ht_result")["outcomes"]}
    assert math.isclose(ht["home_win"] + ht["draw"] + ht["away_win"], 1.0, abs_tol=1e-6)
    # fewer goals by half time -> HT draw more likely than FT draw
    ft = {o["key"]: o["prob"] for o in _group(s, "result")["outcomes"]}
    assert ht["draw"] > ft["draw"]


def test_asian_handicap_ladder_present_and_monotone():
    s = derive_markets(1.7, 1.0)
    ah = _group(s, "asian_handicap")
    covers = {o["key"]: o["prob"] for o in ah["outcomes"]}
    # giving the home team a bigger handicap makes "home covers" less likely
    assert covers["home_-0_5"] > covers["home_-1_5"] > covers["home_-2_5"]
