"""Tournament Monte Carlo.

Simulates the World Cup group stage (and, when a knockout bracket spec is supplied via
``simulate_tournament``, the bracket) by sampling scorelines from the SAME Dixon-Coles
score matrices the per-match model produces, then applying the real WC2026 qualification
rules (top two per group + best-N third-placed teams). Aggregating thousands of runs gives
each team a group-finish / advancement / (with a bracket) title probability.

Design notes
------------
* The simulator is decoupled from the DB and the async input assembly. It takes a plain
  fixture list (``SimMatch``) plus a per-match ``(lambda_home, lambda_away)`` map, so it is
  pure, deterministic under a seed, and unit-testable without network or DB. The async
  ``precompute_group_lambdas`` helper (used by the API route) builds that map from the live
  model so the simulation and the per-match page agree to the goal.
* Completed matches use their actual scoreline every run; only unplayed matches are sampled.
* Goals are sampled from the full normalised DC matrix (so the rho low-score correction and
  the matrix's 0-8 goal cap are respected), NOT from two independent Poissons.
* Tiebreakers follow FIFA order as far as is meaningful in simulation: points, goal
  difference, goals for, then head-to-head (points, GD, GF among the tied teams); any
  remaining exact tie is broken at random (modelling fair-play / drawing of lots, which we
  have no data to simulate). This is a documented simplification.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass

import numpy as np

from backend.models.elo_model import elo_to_lambdas
from backend.models.poisson import build_score_matrix, match_probabilities

_BRACKET_PATH = os.path.join(os.path.dirname(__file__), "wc2026_bracket.json")
_BRACKET_CACHE: dict | None = None

# Official R32 third-place slots and the groups each may receive (from the R32 away slots).
# A best-third combination is valid only if each slot's assigned group is in its pool.
_THIRD_POOLS: dict[str, set] = {
    "M74": set("ABCDF"), "M77": set("CDFGH"), "M79": set("CEFHI"), "M80": set("EHIJK"),
    "M81": set("BEFIJ"), "M82": set("AEHIJ"), "M85": set("EFGIJ"), "M87": set("DEIJL"),
}


def match_thirds(groups) -> dict[str, str]:
    """Deterministic pool-valid perfect matching of the 8 qualifying third-place groups to
    the 8 R32 third slots. A guaranteed-valid fallback used to repair/validate the scraped
    combination table (any combination of 8 groups admits at least one valid matching)."""
    groups = set(groups)
    # most-constrained slot first for fast, deterministic backtracking
    slots = sorted(_THIRD_POOLS, key=lambda s: (len(_THIRD_POOLS[s] & groups), s))
    assign: dict[str, str] = {}
    used: set = set()

    def bt(i: int) -> bool:
        if i == len(slots):
            return True
        slot = slots[i]
        for g in sorted(_THIRD_POOLS[slot] & groups):
            if g in used:
                continue
            assign[slot] = g
            used.add(g)
            if bt(i + 1):
                return True
            used.discard(g)
            del assign[slot]
        return False

    if not bt(0):
        raise ValueError(f"no valid third-place matching for {sorted(groups)}")
    return assign


def _valid_row(asg: dict[str, str]) -> bool:
    return all(g in _THIRD_POOLS[slot] for slot, g in asg.items())


def load_bracket() -> dict:
    """Official WC2026 knockout structure: R32 slot pairings, the winner-feeds tree
    (M89-104), and the 495-row best-third combination table. Self-healing — any row whose
    assignment violates the official slot pools (e.g. a scrape error) is replaced with a
    computed pool-valid matching, so the bracket can never seed a third into an illegal
    slot."""
    global _BRACKET_CACHE
    if _BRACKET_CACHE is None:
        with open(_BRACKET_PATH) as f:
            b = json.load(f)
        repaired = 0
        for key, asg in b["third_table"].items():
            if not _valid_row(asg):
                b["third_table"][key] = match_thirds(key)
                repaired += 1
        if repaired:
            print(f"[bracket] repaired {repaired} invalid third-place row(s)")
        _BRACKET_CACHE = b
    return _BRACKET_CACHE


@dataclass
class SimMatch:
    id: str
    group: str
    home: str  # team code
    away: str
    status: str = "upcoming"
    home_score: int | None = None
    away_score: int | None = None


# --------------------------------------------------------------------------------------
# Group ranking
# --------------------------------------------------------------------------------------

def _empty() -> dict[str, int]:
    return {"pts": 0, "gd": 0, "gf": 0, "ga": 0}


def _table(codes: list[str], results: list[tuple[str, str, int, int]]) -> dict[str, dict]:
    stats = {c: _empty() for c in codes}
    for h, a, gh, ga in results:
        sh, sa = stats[h], stats[a]
        sh["gf"] += gh
        sh["ga"] += ga
        sa["gf"] += ga
        sa["ga"] += gh
        if gh > ga:
            sh["pts"] += 3
        elif ga > gh:
            sa["pts"] += 3
        else:
            sh["pts"] += 1
            sa["pts"] += 1
    for c in codes:
        stats[c]["gd"] = stats[c]["gf"] - stats[c]["ga"]
    return stats


def _h2h_key(cluster: list[str], results: list[tuple[str, str, int, int]]):
    """Mini head-to-head table restricted to matches among the tied `cluster`."""
    members = set(cluster)
    sub = [(h, a, gh, ga) for h, a, gh, ga in results if h in members and a in members]
    stats = _table(cluster, sub)
    return lambda c: (stats[c]["pts"], stats[c]["gd"], stats[c]["gf"])


def rank_group(
    codes: list[str],
    results: list[tuple[str, str, int, int]],
    rng: np.random.Generator,
) -> tuple[list[str], dict[str, dict]]:
    """Return (ordered_codes_best_first, stats)."""
    stats = _table(codes, results)

    def primary(c: str):
        return (stats[c]["pts"], stats[c]["gd"], stats[c]["gf"])

    ordered = sorted(codes, key=primary, reverse=True)

    # Resolve clusters that are level on (pts, gd, gf) via head-to-head, then random.
    out: list[str] = []
    i = 0
    while i < len(ordered):
        j = i + 1
        while j < len(ordered) and primary(ordered[j]) == primary(ordered[i]):
            j += 1
        cluster = ordered[i:j]
        if len(cluster) > 1:
            h2h = _h2h_key(cluster, results)
            # sort by head-to-head desc, with a random jitter to break full ties uniformly
            jitter = {c: rng.random() for c in cluster}
            cluster = sorted(cluster, key=lambda c: (h2h(c), jitter[c]), reverse=True)
        out.extend(cluster)
        i = j
    return out, stats


# --------------------------------------------------------------------------------------
# Sampling
# --------------------------------------------------------------------------------------

def _sample_goals(lh: float, la: float, n: int, rng: np.random.Generator):
    """Vectorised draw of n (home_goals, away_goals) pairs from the DC score matrix."""
    matrix = build_score_matrix(lh, la)
    ncols = matrix.shape[1]
    flat = matrix.ravel()
    cum = np.cumsum(flat)
    cum /= cum[-1]
    u = rng.random(n)
    idx = np.searchsorted(cum, u, side="right")
    idx = np.clip(idx, 0, flat.size - 1)
    gh = (idx // ncols).astype(np.int16)
    ga = (idx % ncols).astype(np.int16)
    return gh, ga


def _match_samples(
    matches: list[SimMatch],
    lambdas: dict[str, tuple[float, float]],
    n: int,
    rng: np.random.Generator,
) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per-match arrays of length n. Completed matches are constant (actual result)."""
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    for m in matches:
        if m.status == "complete" and m.home_score is not None and m.away_score is not None:
            gh = np.full(n, int(m.home_score), dtype=np.int16)
            ga = np.full(n, int(m.away_score), dtype=np.int16)
        else:
            lh, la = lambdas.get(m.id, (1.3, 1.3))
            gh, ga = _sample_goals(lh, la, n, rng)
        out[m.id] = (gh, ga)
    return out


def _group_stage_pass(groups, codes_by_group, samples, s, rng):
    """One simulated group stage: returns {group: [c1,c2,c3,c4]} and {group: {code: stats}}."""
    orders: dict[str, list[str]] = {}
    stats_all: dict[str, dict] = {}
    for g, ms in groups.items():
        results = [(m.home, m.away, int(samples[m.id][0][s]), int(samples[m.id][1][s])) for m in ms]
        order, stats = rank_group(codes_by_group[g], results, rng)
        orders[g] = order
        stats_all[g] = stats
    return orders, stats_all


# --------------------------------------------------------------------------------------
# Group-stage simulation
# --------------------------------------------------------------------------------------

def simulate_group_stage(
    matches: list[SimMatch],
    lambdas: dict[str, tuple[float, float]],
    n_sims: int = 20000,
    seed: int | None = None,
    n_third_qualify: int = 8,
    names: dict[str, str] | None = None,
) -> dict:
    """Monte-Carlo the group stage.

    Returns ``{"n_sims", "teams": [ {code, group, p_first, p_second, p_third,
    p_third_qualify, p_top2, p_advance, exp_points, exp_gd, exp_gf}, ... ]}`` where
    ``p_advance == p_top2 + p_third_qualify`` and probabilities are over the simulations.
    """
    rng = np.random.default_rng(seed)
    names = names or {}

    groups: dict[str, list[SimMatch]] = {}
    for m in matches:
        groups.setdefault(m.group, []).append(m)

    codes_by_group = {
        g: sorted({c for m in ms for c in (m.home, m.away)})
        for g, ms in groups.items()
    }
    all_codes = [c for cs in codes_by_group.values() for c in cs]

    samples = _match_samples(matches, lambdas, n_sims, rng)

    # tallies
    first = {c: 0 for c in all_codes}
    second = {c: 0 for c in all_codes}
    third = {c: 0 for c in all_codes}
    third_q = {c: 0 for c in all_codes}
    pts_sum = {c: 0 for c in all_codes}
    gd_sum = {c: 0 for c in all_codes}
    gf_sum = {c: 0 for c in all_codes}
    group_of = {c: g for g, cs in codes_by_group.items() for c in cs}

    for s in range(n_sims):
        orders, stats_all = _group_stage_pass(groups, codes_by_group, samples, s, rng)
        third_pool: list[tuple[tuple[int, int, int], float, str]] = []
        for g, order in orders.items():
            stats = stats_all[g]
            first[order[0]] += 1
            second[order[1]] += 1
            third[order[2]] += 1
            for c in codes_by_group[g]:
                pts_sum[c] += stats[c]["pts"]
                gd_sum[c] += stats[c]["gd"]
                gf_sum[c] += stats[c]["gf"]
            t = order[2]
            st = stats[t]
            third_pool.append(((st["pts"], st["gd"], st["gf"]), rng.random(), t))

        # Best-N third-placed teams qualify.
        third_pool.sort(key=lambda x: (x[0], x[1]), reverse=True)
        for _key, _j, code in third_pool[:n_third_qualify]:
            third_q[code] += 1

    n = float(n_sims)
    rows = []
    for c in all_codes:
        p_first = first[c] / n
        p_second = second[c] / n
        p_third = third[c] / n
        p_tq = third_q[c] / n
        p_top2 = p_first + p_second
        rows.append({
            "code": c,
            "name": names.get(c, c),
            "group": group_of[c],
            "p_first": round(p_first, 4),
            "p_second": round(p_second, 4),
            "p_third": round(p_third, 4),
            "p_third_qualify": round(p_tq, 4),
            "p_top2": round(p_top2, 4),
            "p_advance": round(p_top2 + p_tq, 4),
            "exp_points": round(pts_sum[c] / n, 3),
            "exp_gd": round(gd_sum[c] / n, 3),
            "exp_gf": round(gf_sum[c] / n, 3),
        })
    rows.sort(key=lambda r: (r["p_advance"], r["p_first"]), reverse=True)
    return {"n_sims": n_sims, "teams": rows}


# --------------------------------------------------------------------------------------
# Full-tournament simulation (group stage + official knockout bracket)
# --------------------------------------------------------------------------------------

def _make_adv_fn(team_elos: dict[str, float]):
    """Memoised P(team a advances over team b) at a neutral venue.

    Uses the same confederation-aware ELO->lambda + DC matrix as the match model, then
    treats a regulation draw as a coin-flip shootout (penalty shootouts are close to
    random; a mild strength lean would barely move title odds)."""
    cache: dict[tuple[str, str], float] = {}

    def adv(a: str, b: str) -> float:
        key = (a, b)
        if key in cache:
            return cache[key]
        rk = (b, a)
        if rk in cache:
            p = 1.0 - cache[rk]
            cache[key] = p
            return p
        lh, la = elo_to_lambdas(team_elos.get(a, 1500.0), team_elos.get(b, 1500.0), a, b)
        mp = match_probabilities(build_score_matrix(lh, la))
        p = mp["home_win"] + 0.5 * mp["draw"]
        cache[key] = p
        return p

    return adv


def _resolve_r32(orders, qualifying_groups, third_table, r32):
    key = "".join(sorted(qualifying_groups))
    assignment = third_table[key]  # {"M74": "F", ...}

    def resolve(slot: str, match_no: int) -> str:
        kind = slot[0]
        if kind == "1":
            return orders[slot[1]][0]
        if kind == "2":
            return orders[slot[1]][1]
        return orders[assignment[f"M{match_no}"]][2]  # third-placed team

    return {mm["match"]: (resolve(mm["home"], mm["match"]), resolve(mm["away"], mm["match"])) for mm in r32}


def _ref(slot: str, winner: dict, loser: dict) -> str:
    n = int(slot[1:])
    return winner[n] if slot[0] == "W" else loser[n]


def simulate_tournament(
    matches: list[SimMatch],
    lambdas: dict[str, tuple[float, float]],
    team_elos: dict[str, float],
    bracket: dict | None = None,
    n_sims: int = 20000,
    seed: int | None = None,
    names: dict[str, str] | None = None,
) -> dict:
    """Group stage + official WC2026 knockout bracket. Adds per-team reach-round and title
    probabilities on top of the group-stage outputs."""
    bracket = bracket or load_bracket()
    rng = np.random.default_rng(seed)
    names = names or {}
    r32, tree, third_table = bracket["r32"], sorted(bracket["tree"], key=lambda t: t["match"]), bracket["third_table"]
    adv = _make_adv_fn(team_elos)

    groups: dict[str, list[SimMatch]] = {}
    for m in matches:
        groups.setdefault(m.group, []).append(m)
    codes_by_group = {g: sorted({c for m in ms for c in (m.home, m.away)}) for g, ms in groups.items()}
    all_codes = [c for cs in codes_by_group.values() for c in cs]
    group_of = {c: g for g, cs in codes_by_group.items() for c in cs}

    samples = _match_samples(matches, lambdas, n_sims, rng)

    z = lambda: {c: 0 for c in all_codes}  # noqa: E731
    first, second, third, third_q = z(), z(), z(), z()
    r16, qf, sf, final, title = z(), z(), z(), z(), z()
    pts_sum, gd_sum, gf_sum = z(), z(), z()
    # How often each team contests each knockout match (73-104), so the bracket view can
    # show the most-likely matchup at every node. The champion it surfaces is the team that
    # wins match 104 most often, which is exactly p_title, so the bracket and the title odds
    # never disagree.
    match_part: dict[int, dict[str, int]] = {mno: {} for mno in range(73, 105)}

    for s in range(n_sims):
        orders, stats_all = _group_stage_pass(groups, codes_by_group, samples, s, rng)
        third_pool = []
        for g, order in orders.items():
            stats = stats_all[g]
            first[order[0]] += 1
            second[order[1]] += 1
            third[order[2]] += 1
            for c in codes_by_group[g]:
                pts_sum[c] += stats[c]["pts"]
                gd_sum[c] += stats[c]["gd"]
                gf_sum[c] += stats[c]["gf"]
            t = order[2]
            st = stats[t]
            third_pool.append(((st["pts"], st["gd"], st["gf"]), rng.random(), t))

        third_pool.sort(key=lambda x: (x[0], x[1]), reverse=True)
        qualifiers = [code for _k, _j, code in third_pool[:8]]
        for code in qualifiers:
            third_q[code] += 1
        qualifying_groups = [group_of[c] for c in qualifiers]

        teams_r32 = _resolve_r32(orders, qualifying_groups, third_table, r32)
        winner: dict[int, str] = {}
        loser: dict[int, str] = {}

        def _play(mno, h, a):
            mp = match_part[mno]
            mp[h] = mp.get(h, 0) + 1
            mp[a] = mp.get(a, 0) + 1
            if rng.random() < adv(h, a):
                winner[mno], loser[mno] = h, a
            else:
                winner[mno], loser[mno] = a, h

        for mno in sorted(teams_r32):  # R32: 73-88
            _play(mno, *teams_r32[mno])
        for tm in tree:  # 89-104 in order
            _play(tm["match"], _ref(tm["home"], winner, loser), _ref(tm["away"], winner, loser))

        for mno in range(73, 89):
            r16[winner[mno]] += 1
        for mno in range(89, 97):
            qf[winner[mno]] += 1
        for mno in range(97, 101):
            sf[winner[mno]] += 1
        for mno in (101, 102):
            final[winner[mno]] += 1
        title[winner[104]] += 1

    n = float(n_sims)
    rows = []
    for c in all_codes:
        p_first = first[c] / n
        p_second = second[c] / n
        p_tq = third_q[c] / n
        p_top2 = p_first + p_second
        rows.append({
            "code": c,
            "name": names.get(c, c),
            "group": group_of[c],
            "p_first": round(p_first, 4),
            "p_second": round(p_second, 4),
            "p_third": round(third[c] / n, 4),
            "p_third_qualify": round(p_tq, 4),
            "p_top2": round(p_top2, 4),
            "p_advance": round(p_top2 + p_tq, 4),
            "p_r16": round(r16[c] / n, 4),
            "p_quarter": round(qf[c] / n, 4),
            "p_semi": round(sf[c] / n, 4),
            "p_final": round(final[c] / n, 4),
            "p_title": round(title[c] / n, 4),
            "exp_points": round(pts_sum[c] / n, 3),
            "exp_gd": round(gd_sum[c] / n, 3),
            "exp_gf": round(gf_sum[c] / n, 3),
        })
    rows.sort(key=lambda r: (r["p_title"], r["p_advance"]), reverse=True)

    # Projected bracket: the two most likely teams to contest each knockout match.
    def _top_parts(mno, k=2):
        items = sorted(match_part[mno].items(), key=lambda kv: kv[1], reverse=True)[:k]
        return [{"code": c, "p": round(cnt / n, 4)} for c, cnt in items]

    r32_by_no = {m["match"]: m for m in r32}
    tree_by_no = {m["match"]: m for m in tree}
    round_spans = [
        ("Round of 32", range(73, 89)),
        ("Round of 16", range(89, 97)),
        ("Quarter-finals", range(97, 101)),
        ("Semi-finals", range(101, 103)),
        ("Final", range(104, 105)),
    ]
    bracket_rounds = []
    for rname, span in round_spans:
        ms = []
        for mno in span:
            node = {"match": mno, "teams": _top_parts(mno, 2)}
            if mno in r32_by_no:
                node["home_rule"], node["away_rule"] = r32_by_no[mno]["home"], r32_by_no[mno]["away"]
            elif mno in tree_by_no:
                node["home_src"], node["away_src"] = tree_by_no[mno]["home"], tree_by_no[mno]["away"]
            ms.append(node)
        bracket_rounds.append({"name": rname, "matches": ms})

    return {
        "n_sims": n_sims,
        "teams": rows,
        "has_knockout": True,
        "bracket": {"rounds": bracket_rounds, "third_place": _top_parts(103, 2)},
    }
