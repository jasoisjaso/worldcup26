"""Model-picked balanced multis — the daily curated edge plays.

What this does
==============
For every upcoming match in the next ~36h, this module:
  1) Builds the score grid from the match's Dixon-Coles lambdas.
  2) Tests a handful of curated same-game-multi (SGM) shapes — these are the
     ones where positive correlation often gives the bookmaker's standard
     joint-pricing model the slip.
  3) Also tests 2-leg cross-match combos drawn from the slate's value board.
  4) Filters every candidate against three rules so we never publish chalk
     OR lottery tickets:
       - combined model probability in [0.12, 0.40]
       - edge over best-available bookie at least +5%
       - at least one leg with a per-leg edge >= 3% (so the multi isn't
         carried by a single fluky model number)
  5) Scores each survivor with the Balanced metric used by the bet builder:
        score = combined_prob * ln(1 + edge_above_market)
  6) De-duplicates so we never publish two multis sharing >=2 legs.
  7) Keeps the top 3-5 picks per day, persists them as ModelMulti rows.

Settler
=======
settle_finished_multis() runs after every score refresh. For each pending
ModelMulti where all legs have results, mark each leg as won/lost using the
match's home_score/away_score and the leg's market, then mark the multi
won/lost + record profit/loss in units (1-unit flat stake assumed).
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy.orm import Session

from backend.betting import multi_analyzer
from backend.betting.kelly import quarter_kelly
from backend.betting.market import devig_shin
from backend.betting.pick_guardrails import grade_pick as _grade_pick
from backend.betting.sgm import joint_probability_from_grid
from backend.data.fetchers.odds import get_book_odds_for_match
from backend.db.models import (
    Match, ModelMulti, ModelMultiLeg, PredictionSnapshot, Team,
)
from backend.db.session import SessionLocal
from backend.models.poisson import build_score_matrix

logger = logging.getLogger(__name__)

# Shape of an SGM the picker is allowed to consider. Each tuple is N market
# keys — these are the canonical correlated bets bookmakers typically price
# too low or too high, i.e. where our grid has an edge. Pairs are the default;
# triples are only published when every leg also clears the stricter per-leg
# edge floor for N=3 (see MIN_PER_LEG_EDGE_BY_N below).
SGM_SHAPES: list[tuple[str, ...]] = [
    # 2-leg shapes (the original SGM_PAIRS)
    ("home_win", "btts"),
    ("home_win", "over_1_5"),
    ("home_win", "over_2_5"),
    ("away_win", "btts"),
    ("away_win", "over_1_5"),
    ("draw", "btts"),
    ("draw", "under_2_5"),
    ("btts", "over_2_5"),
    ("btts", "over_1_5"),
    ("1x", "over_1_5"),
    ("x2", "over_1_5"),
    ("under_2_5", "btts_no"),
    # 3-leg shapes — high-correlation triples the bookie often misprices.
    # Classic favourite goalfest / upset goalfest / dead-rubber tight game.
    ("home_win", "over_2_5", "btts"),
    ("away_win", "over_2_5", "btts"),
    ("draw", "under_2_5", "btts_no"),
]

# Combined-prob band: don't publish boring chalk (>40%) or lottery tickets (<5%).
# The lower bound shifts with leg count (see MIN_COMBINED_BY_N) because three
# 60% legs land 22% of the time, four land 13%, five land 8%.
MAX_COMBINED = 0.40
MAX_PICKS_PER_DAY = 5
PICK_LOOKAHEAD_HOURS = 36

# --- Leg-count escalation -------------------------------------------------
# Conservative table: more legs = compounded vig grows, so every leg has to
# do more EV work to clear the bar. Five-fold is essentially unreachable on
# a WC slate and is left out on purpose. See
# docs/research/2026-06-24_model-multis-improvement.md for the derivation.
MAX_LEGS = 4
MIN_COMBINED_BY_N: dict[int, float] = {2: 0.12, 3: 0.10, 4: 0.07}
MIN_EDGE_OVER_BOOK_BY_N: dict[int, float] = {2: 0.05, 3: 0.05, 4: 0.05}
MIN_PER_LEG_EDGE_BY_N: dict[int, float] = {2: 0.03, 3: 0.05, 4: 0.07}

# Hard ceiling on compounded bookmaker margin across all legs. A 5% margin
# per leg compounds to ~22.6% on a 5-fold, so even a "model EV looks good"
# multi can be entirely chewed up by overround. 0.20 = 20% built-in
# disadvantage is our absolute cut-off.
MAX_COMPOUNDED_MARGIN = 0.20

# Two cross-match legs whose kickoffs fall within this many minutes of each
# other share weather, news-shock and same-window correlation risk. Cap how
# many same-window legs can appear in one multi (see dedupe logic).
KICKOFF_WINDOW_MINUTES = 30

# Mean-CLV cap used to score-bias multi candidates. clv_bias = 1 + alpha*mean_clv,
# clamped to [-cap, +cap] so a single unlucky market doesn't tank a multi nor
# does a single hot streak send it stratospheric.
CLV_BIAS_ALPHA = 1.5
CLV_BIAS_CLAMP = 0.30  # ±30% nudge max
CLV_LOOKBACK = 30      # last N settled picks per market

# Cache so we don't re-query the DB once per candidate.
_CLV_BIAS_CACHE: dict[str, float] = {}


@dataclass
class _Candidate:
    kind: str                                 # "sgm" or "cross"
    label: str
    combined_prob: float
    combined_book_odds: float
    leg_specs: list[dict]                     # one dict per leg with all the fields ModelMultiLeg needs
    score: float


# --- Helpers for the leg-count escalation + new filters -------------------

def _per_leg_overround(book_prices_for_group: list[float]) -> float | None:
    """Bookmaker overround for the market group these prices belong to.
    e.g. for a 1X2 leg, pass [home_win_price, draw_price, away_win_price] —
    sum(1/o) - 1 is the embedded margin. None when any price is missing."""
    if not book_prices_for_group or any(p is None or p <= 1.0 for p in book_prices_for_group):
        return None
    s = sum(1.0 / p for p in book_prices_for_group)
    return max(0.0, s - 1.0)


# Which market-group of prices each leg's overround should be measured against.
# We need the COMPLEMENT prices to compute the per-leg overround, not just the
# leg's own price. e.g. a home_win leg's vig is encoded in the full 1X2 triple.
_LEG_GROUP_KEYS: dict[str, tuple[str, ...]] = {
    "home_win": ("home_win", "draw", "away_win"),
    "draw":     ("home_win", "draw", "away_win"),
    "away_win": ("home_win", "draw", "away_win"),
    "1x":       ("home_win", "draw", "away_win"),
    "x2":       ("home_win", "draw", "away_win"),
    "12":       ("home_win", "draw", "away_win"),
    "over_2_5":  ("over_2_5", "under_2_5"),
    "under_2_5": ("over_2_5", "under_2_5"),
    "btts":    ("btts", "btts_no"),
    "btts_no": ("btts", "btts_no"),
    # 1.5 / 3.5 over-unders aren't always shipped as complementary pairs by the
    # Odds API; fall back to single-side implied probability when absent.
    "over_1_5": ("over_1_5",),
    "over_3_5": ("over_3_5",),
}


def _compounded_margin(legs: list[dict], book_by_match: dict[str, dict]) -> float | None:
    """Compounded bookmaker margin across all legs in a multi.

    For each leg, look up the per-leg overround using the FULL price group
    for that leg's market (e.g. all three 1X2 prices for a home_win leg).
    Multiply (1 + per-leg margin) across legs and subtract 1 — that's the
    total built-in disadvantage the multi has to overcome.
    """
    factor = 1.0
    seen_groups: set[tuple[str, tuple[str, ...]]] = set()
    for leg in legs:
        mid = leg["match_id"]
        market = leg["market"]
        group_keys = _LEG_GROUP_KEYS.get(market)
        if not group_keys:
            # Unknown market — be conservative, assume a typical 5% overround.
            factor *= 1.05
            continue
        # Two legs from the same match in the same market group share one
        # margin (we already paid for that vig once); skip duplicates.
        sig = (mid, group_keys)
        if sig in seen_groups:
            continue
        seen_groups.add(sig)
        book = book_by_match.get(mid) or {}
        prices = [book.get(k, {}).get("best_price") for k in group_keys]
        if any(p is None for p in prices) and len(group_keys) > 1:
            # Missing a complement price — fall back to single-side implied.
            single = book.get(market, {}).get("best_price")
            if single and single > 1.0:
                factor *= (1.0 + max(0.0, 1.0 / single - 0.5))  # rough fallback
            continue
        per_leg = _per_leg_overround([p for p in prices if p is not None])
        if per_leg is None:
            factor *= 1.05
            continue
        factor *= (1.0 + per_leg)
    return factor - 1.0


def _leg_beneficiary(leg: dict) -> str | None:
    """Team-code this leg banks on (for the same-team-twice dedupe).
    Draws and goal markets don't lock a single team."""
    mid = leg.get("match_id")
    market = leg.get("market")
    if not (mid and market):
        return None
    # Caller must populate home_code/away_code via the match-context lookup;
    # without those we can only block based on raw match_id (already handled).
    if market == "home_win":
        return leg.get("home_code")
    if market == "away_win":
        return leg.get("away_code")
    return None


def _kickoff_window_key(kickoff: datetime | None, window_min: int = KICKOFF_WINDOW_MINUTES) -> int | None:
    """Bucket a kickoff into a (window_min)-minute slot. Two kickoffs landing in
    the same bucket are 'same window' for correlation purposes."""
    if not kickoff:
        return None
    epoch_min = int(kickoff.timestamp() // 60)
    return epoch_min // window_min


def _violates_diversification(legs: list[dict]) -> str | None:
    """Cross-match diversification check. Returns a reason string when the
    combo is too correlated, or None when it's diverse enough to publish.

    Rules:
      1. No two legs benefit the same team.
      2. No two legs sit in the same WC group (group-stage cross-correlation).
      3. No two legs share the same ±30min kickoff window.
    """
    seen_teams: set[str] = set()
    for leg in legs:
        team = _leg_beneficiary(leg)
        if team:
            if team in seen_teams:
                return f"same team locked twice ({team})"
            seen_teams.add(team)

    groups: list[str] = [str(leg["group"]) for leg in legs if leg.get("group")]
    if len(groups) != len(set(groups)):
        # Two legs in the same WC group — group-stage results are correlated.
        dup = [g for g in set(groups) if groups.count(g) > 1]
        return f"two legs in same group ({', '.join(dup)})"

    windows = [_kickoff_window_key(leg.get("kickoff")) for leg in legs]
    windows_present = [w for w in windows if w is not None]
    if len(windows_present) != len(set(windows_present)):
        return "two legs in the same kickoff window"

    return None


def _clv_bias_for_market(db: Session, market: str) -> float:
    """Score multiplier reflecting how our model has performed historically
    on this market vs the closing line. mean_clv > 0 = we've been beating
    the close on this market type → scale up its multi-score modestly.

    Returns 1.0 (no bias) when fewer than 5 settled picks are available.
    Cached per market for the lifetime of the process; the generator only
    runs a couple of times an hour so this is fine.
    """
    if market in _CLV_BIAS_CACHE:
        return _CLV_BIAS_CACHE[market]
    from backend.db.models import Prediction
    rows = (
        db.query(Prediction.clv)
        .filter(Prediction.market == market, Prediction.clv.isnot(None))
        .order_by(Prediction.logged_at.desc())
        .limit(CLV_LOOKBACK)
        .all()
    )
    clv_vals = [r[0] for r in rows if r[0] is not None]
    if len(clv_vals) < 5:
        _CLV_BIAS_CACHE[market] = 1.0
        return 1.0
    mean_clv = sum(clv_vals) / len(clv_vals)
    raw = CLV_BIAS_ALPHA * mean_clv
    clamped = max(-CLV_BIAS_CLAMP, min(CLV_BIAS_CLAMP, raw))
    bias = 1.0 + clamped
    _CLV_BIAS_CACHE[market] = bias
    return bias


def _steam_against_pick(match_id: str, market: str, model_prob: float) -> bool:
    """True when sharp money has moved the line AGAINST our pick. Used to
    drop a leg even when our static EV looks good — line movement is the
    market's real-time updated opinion, and when it's contradicting us we
    should listen."""
    from backend.data.fetchers.odds import get_steam_signal
    signal = get_steam_signal(match_id, market, model_prob)
    return bool(signal and signal.get("direction") == "fading" and signal.get("move_pct", 0) >= 2.0)


def _grid_for_match(snap: PredictionSnapshot):
    if snap.lambda_home is None or snap.lambda_away is None:
        return None
    return build_score_matrix(snap.lambda_home, snap.lambda_away, max_goals=10)


def _model_prob(grid, market: str) -> float | None:
    masks = multi_analyzer.expand_market(market)
    if not masks:
        return None
    return joint_probability_from_grid(grid, masks)


def _devig_1x2(book_odds: dict) -> dict[str, float] | None:
    """Returns devig PROBABILITIES (not prices) by market key."""
    h = book_odds.get("home_win", {}).get("best_price")
    d = book_odds.get("draw", {}).get("best_price")
    a = book_odds.get("away_win", {}).get("best_price")
    if not (h and d and a):
        return None
    fp = devig_shin([h, d, a])
    if not fp:
        return None
    return {"home_win": fp[0], "draw": fp[1], "away_win": fp[2]}


def _devig_two_way(book_odds: dict, key_pos: str, key_neg: str) -> dict[str, float] | None:
    """Returns devig PROBABILITIES (not prices) by market key."""
    p = book_odds.get(key_pos, {}).get("best_price")
    n = book_odds.get(key_neg, {}).get("best_price")
    if not (p and n):
        return None
    fp = devig_shin([p, n])
    if not fp:
        return None
    return {key_pos: fp[0], key_neg: fp[1]}


def _build_match_context(db: Session, m: Match) -> dict | None:
    snap = db.query(PredictionSnapshot).filter(PredictionSnapshot.match_id == m.id).first()
    if not snap or snap.lambda_home is None or snap.lambda_away is None:
        return None
    grid = _grid_for_match(snap)
    if grid is None:
        return None
    book = get_book_odds_for_match(m.id)
    if not book:
        return None
    home = db.query(Team).filter(Team.code == m.home_code).first()
    away = db.query(Team).filter(Team.code == m.away_code).first()
    if not home or not away:
        return None
    # Combined devig 1X2 + OU 2.5 + BTTS. Also derive double-chance probabilities
    # from the 1X2 so the picker can use 1X / X2 / 12 legs with a real edge baseline.
    devig: dict[str, float] = {}
    one_x_two = _devig_1x2(book)
    if one_x_two:
        devig.update(one_x_two)
        devig["1x"] = one_x_two["home_win"] + one_x_two["draw"]
        devig["x2"] = one_x_two["draw"] + one_x_two["away_win"]
        devig["12"] = one_x_two["home_win"] + one_x_two["away_win"]
    ou = _devig_two_way(book, "over_2_5", "under_2_5")
    if ou:
        devig.update(ou)
    btts = _devig_two_way(book, "btts", "btts_no")
    if btts:
        devig.update(btts)
    return {
        "match": m, "grid": grid, "home": home, "away": away,
        "book": book, "devig": devig,
    }


def _resolve_leg_price(book: dict, market: str) -> float | None:
    """Return the best book price for the leg, composing double-chance from
    the 1X2 odds when the Odds API didn't ship 1X / X2 / 12 directly."""
    direct = book.get(market, {}).get("best_price")
    if direct:
        return direct
    if market == "1x":
        h = book.get("home_win", {}).get("best_price")
        d = book.get("draw", {}).get("best_price")
        if h and d:
            # Fair-price composition assuming independence between H and D — they
            # are mutually exclusive, so the implied prob is sum of (1/h)+(1/d).
            return round(1.0 / (1.0 / h + 1.0 / d), 3)
        return None
    if market == "x2":
        d = book.get("draw", {}).get("best_price")
        a = book.get("away_win", {}).get("best_price")
        if d and a:
            return round(1.0 / (1.0 / d + 1.0 / a), 3)
        return None
    if market == "12":
        h = book.get("home_win", {}).get("best_price")
        a = book.get("away_win", {}).get("best_price")
        if h and a:
            return round(1.0 / (1.0 / h + 1.0 / a), 3)
        return None
    return None


def _candidates_from_match(
    ctx: dict,
    clv_bias_by_market: dict[str, float] | None = None,
) -> list[_Candidate]:
    out: list[_Candidate] = []
    m: Match = ctx["match"]
    home, away = ctx["home"].name, ctx["away"].name
    grid = ctx["grid"]
    book = ctx["book"]
    devig = ctx["devig"]
    clv_bias_by_market = clv_bias_by_market or {}

    for shape in SGM_SHAPES:
        n = len(shape)
        if n < 2 or n > MAX_LEGS:
            continue

        # Per-leg prices. Doubles 1X/X2 don't ship from the Odds API directly —
        # compose them from H+D / D+A when possible.
        leg_prices: list[float | None] = [_resolve_leg_price(book, mkt) for mkt in shape]
        if any(p is None for p in leg_prices):
            continue

        # Joint comes straight off the score grid: the AND of every leg's
        # masks scored against the Dixon-Coles distribution IS the true
        # correlated joint, including for non-overlapping mask sets like
        # ("home_win", "over_2_5", "btts"). Multiplying P(a)*P(b)*P(c) silently
        # discards the correlation edge that's exactly what makes the SGM +EV.
        joint_keys: set[str] = set()
        bad_market = False
        for mkt in shape:
            masks = multi_analyzer.expand_market(mkt)
            if not masks:
                bad_market = True
                break
            joint_keys.update(masks)
        if bad_market:
            continue
        joint_prob = joint_probability_from_grid(grid, list(joint_keys))
        if joint_prob is None or joint_prob <= 0:
            continue

        combined_book_odds = 1.0
        for p in leg_prices:
            combined_book_odds *= float(p)  # type: ignore[arg-type]

        # Per-leg edges + GUARDRAIL. Every leg must be a CORE-grade edge
        # (believable, sample-backed, under the absolute-EV cap) before the
        # multi is allowed. Also drop any leg the sharp market is fading.
        per_leg_edges: list[float] = []
        leg_rejected = False
        for mkt, leg_price in zip(shape, leg_prices):
            mp = _model_prob(grid, mkt)
            implied = devig.get(mkt)
            if _grade_pick(model_prob=mp or 0.0, market_implied=implied,
                           book_odds=leg_price, sample=40).tier == "reject":
                leg_rejected = True
                break
            if mp and _steam_against_pick(m.id, mkt, mp):
                leg_rejected = True
                break
            if mp and implied and implied > 0:
                per_leg_edges.append(mp / implied - 1.0)
        if leg_rejected:
            continue

        # Per-N escalation: bigger multi → every leg has to do more work.
        per_leg_floor = MIN_PER_LEG_EDGE_BY_N.get(n, MIN_PER_LEG_EDGE_BY_N[MAX_LEGS])
        if not per_leg_edges or min(per_leg_edges) < per_leg_floor:
            continue

        # Combined edge vs bookie + per-N floors.
        combined_edge = joint_prob * combined_book_odds - 1.0
        if combined_edge < MIN_EDGE_OVER_BOOK_BY_N.get(n, MIN_EDGE_OVER_BOOK_BY_N[MAX_LEGS]):
            continue
        prob_floor = MIN_COMBINED_BY_N.get(n, MIN_COMBINED_BY_N[MAX_LEGS])
        if joint_prob < prob_floor or joint_prob > MAX_COMBINED:
            continue

        # Build leg specs (also needed for the compounded-margin check).
        leg_specs: list[dict] = []
        for i, mkt in enumerate(shape):
            mp = _model_prob(grid, mkt)
            leg_specs.append({
                "leg_order": i + 1,
                "match_id": m.id,
                "market": mkt,
                "market_label": multi_analyzer.market_label(mkt),
                "model_prob": mp,
                "market_implied_prob": devig.get(mkt),
                "book_odds": book.get(mkt, {}).get("best_price"),
                "book_name": book.get(mkt, {}).get("best_book"),
            })

        # Compounded-margin gate — the silent EV killer on multi-leg shapes.
        comp = _compounded_margin(leg_specs, {m.id: book})
        if comp is not None and comp > MAX_COMPOUNDED_MARGIN:
            continue

        # CLV bias: weighted geometric mean of per-leg market biases.
        biases = [clv_bias_by_market.get(mkt, 1.0) for mkt in shape]
        clv_factor = math.prod(biases) ** (1.0 / len(biases)) if biases else 1.0

        score = joint_prob * math.log(1.0 + combined_edge) * clv_factor

        label_markets = " + ".join(multi_analyzer.market_label(mkt) for mkt in shape)
        out.append(_Candidate(
            kind="sgm",
            label=f"{home} v {away}: {label_markets}",
            combined_prob=joint_prob,
            combined_book_odds=combined_book_odds,
            leg_specs=leg_specs,
            score=score,
        ))
    return out


def _cross_match_candidates(
    contexts: list[dict],
    clv_bias_by_market: dict[str, float] | None = None,
) -> list[_Candidate]:
    """Best cross-match 2..MAX_LEGS combos drawn from each match's strongest
    single edge (the leg with highest model_prob/implied ratio that beats the
    per-N edge floor). Adds independence + compounded-margin filters."""
    from itertools import combinations
    clv_bias_by_market = clv_bias_by_market or {}

    best_legs: list[dict] = []
    book_by_match: dict[str, dict] = {}
    for ctx in contexts:
        m: Match = ctx["match"]
        home, away = ctx["home"].name, ctx["away"].name
        grid = ctx["grid"]
        book = ctx["book"]
        devig = ctx["devig"]
        book_by_match[m.id] = book
        best_for_match = None
        best_ratio = 0.0
        for mkt in ("home_win", "draw", "away_win", "btts", "over_2_5", "under_2_5"):
            mp = _model_prob(grid, mkt)
            implied = devig.get(mkt)
            book_price = book.get(mkt, {}).get("best_price")
            if not (mp and implied and book_price):
                continue
            # GUARDRAIL: only believable, capped edges may seed a cross-match
            # multi. Rejects the implausible-edge legs (the +68% EV failure mode).
            if _grade_pick(model_prob=mp, market_implied=implied,
                           book_odds=book_price, sample=40).tier == "reject":
                continue
            # Drop the leg if sharp money is fading our pick.
            if _steam_against_pick(m.id, mkt, mp):
                continue
            ratio = mp / implied
            if ratio > best_ratio and ratio >= 1.06:
                best_ratio = ratio
                best_for_match = {
                    "leg_order": 0,  # set later
                    "match_id": m.id,
                    "match_label": f"{home} v {away}",
                    "market": mkt,
                    "market_label": multi_analyzer.market_label(mkt),
                    "model_prob": mp,
                    "market_implied_prob": implied,
                    "book_odds": book_price,
                    "book_name": book.get(mkt, {}).get("best_book"),
                    # Diversification context (used by _violates_diversification).
                    "home_code": m.home_code,
                    "away_code": m.away_code,
                    "group": m.group,
                    "kickoff": m.kickoff,
                }
        if best_for_match:
            best_legs.append(best_for_match)

    out: list[_Candidate] = []
    # Iterate 2..MAX_LEGS — each size has its own thresholds. We do NOT
    # collapse to "always the biggest combo" because a 4-leg only earns
    # its place when every leg clears the harder 4-leg floor.
    for n in range(2, MAX_LEGS + 1):
        if len(best_legs) < n:
            break
        per_leg_floor = MIN_PER_LEG_EDGE_BY_N.get(n, MIN_PER_LEG_EDGE_BY_N[MAX_LEGS])
        edge_floor = MIN_EDGE_OVER_BOOK_BY_N.get(n, MIN_EDGE_OVER_BOOK_BY_N[MAX_LEGS])
        prob_floor = MIN_COMBINED_BY_N.get(n, MIN_COMBINED_BY_N[MAX_LEGS])

        for combo in combinations(best_legs, n):
            # Independence + diversification gates (group / kickoff / team).
            if _violates_diversification(list(combo)):
                continue

            # Each leg must clear the per-N edge floor on its own.
            edges = [
                (leg["model_prob"] / leg["market_implied_prob"] - 1.0)
                if leg.get("market_implied_prob") else 0.0
                for leg in combo
            ]
            if min(edges) < per_leg_floor:
                continue

            joint_prob = 1.0
            combined_book = 1.0
            for leg in combo:
                joint_prob *= float(leg["model_prob"])
                combined_book *= float(leg["book_odds"])

            if joint_prob < prob_floor or joint_prob > MAX_COMBINED:
                continue

            edge = joint_prob * combined_book - 1.0
            if edge < edge_floor:
                continue

            leg_specs = [{**leg, "leg_order": i + 1} for i, leg in enumerate(combo)]

            # Compounded-margin gate.
            comp = _compounded_margin(leg_specs, book_by_match)
            if comp is not None and comp > MAX_COMPOUNDED_MARGIN:
                continue

            # CLV bias by market (geometric mean over legs).
            biases = [clv_bias_by_market.get(leg["market"], 1.0) for leg in combo]
            clv_factor = math.prod(biases) ** (1.0 / len(biases)) if biases else 1.0

            score = joint_prob * math.log(1.0 + edge) * clv_factor

            label = " + ".join(
                f"{leg['match_label']}: {leg['market_label']}" for leg in combo
            )
            out.append(_Candidate(
                kind="cross",
                label=label,
                combined_prob=joint_prob,
                combined_book_odds=combined_book,
                leg_specs=leg_specs,
                score=score,
            ))
    return out


def _dedupe(candidates: Iterable[_Candidate]) -> list[_Candidate]:
    """Pick a diverse top-N by score. Rules:
    1. Drop a candidate if it shares >=2 legs with an already-kept one.
    2. Cap how many kept picks can share any single (match, market) leg at
       MAX_LEG_REPEAT — keeps the board readable when one team has a huge edge.
    """
    MAX_LEG_REPEAT = 2
    kept: list[_Candidate] = []
    leg_count: dict[tuple[str, str], int] = {}
    for c in sorted(candidates, key=lambda x: x.score, reverse=True):
        sig = {(l["match_id"], l["market"]) for l in c.leg_specs}
        # Rule 1
        clash = any(len(sig & {(l["match_id"], l["market"]) for l in k.leg_specs}) >= 2 for k in kept)
        if clash:
            continue
        # Rule 2
        over_cap = any(leg_count.get(leg, 0) >= MAX_LEG_REPEAT for leg in sig)
        if over_cap:
            continue
        kept.append(c)
        for leg in sig:
            leg_count[leg] = leg_count.get(leg, 0) + 1
        if len(kept) >= MAX_PICKS_PER_DAY:
            break
    return kept


def generate_daily_picks() -> dict:
    """Build today's batch of model multis. Idempotent — refuses to create new
    picks if any pending multis are already in the system for matches that
    haven't kicked off yet."""
    db = SessionLocal()
    try:
        now = datetime.utcnow()

        # Don't double-publish if we already have enough LIVE pending picks — but
        # only count picks that are genuinely still open (at least one leg's match
        # hasn't finished). A pending multi whose legs are ALL complete is merely
        # awaiting settlement, not an active pick; counting it here let a single
        # un-settled finished multi pin the count at the cap and silently stall
        # all new generation (the board went stale from 2026-07-04). Settlement
        # runs immediately before this in the tick, so normally these are already
        # cleared — this guard just makes the stall impossible if settlement lags.
        live_pending = 0
        for mm in db.query(ModelMulti).filter(ModelMulti.status == "pending").all():
            legs = db.query(ModelMultiLeg).filter(ModelMultiLeg.multi_id == mm.id).all()
            all_finished = bool(legs) and all(
                (db.get(Match, l.match_id) is not None
                 and db.get(Match, l.match_id).status == "complete")
                for l in legs
            )
            if not all_finished:
                live_pending += 1
        if live_pending >= MAX_PICKS_PER_DAY:
            return {"status": "already_picked", "pending": live_pending}

        upcoming = (
            db.query(Match)
            .filter(Match.status != "complete")
            .filter(Match.kickoff > now + timedelta(minutes=15))   # need lead time so we're not picking against a kickoff
            .filter(Match.kickoff < now + timedelta(hours=PICK_LOOKAHEAD_HOURS))
            .order_by(Match.kickoff.asc())
            .all()
        )
        if not upcoming:
            return {"status": "no_matches"}

        contexts = []
        for m in upcoming:
            ctx = _build_match_context(db, m)
            if ctx:
                contexts.append(ctx)

        # Pre-compute per-market CLV bias once per generation run so we don't
        # hammer the DB inside the per-candidate hot loop. Cache is module-
        # global with TTL = process lifetime; the scheduler tick is the
        # natural invalidation boundary, so we clear it here.
        _CLV_BIAS_CACHE.clear()
        clv_bias: dict[str, float] = {}
        for mkt in (
            "home_win", "draw", "away_win", "1x", "x2", "12",
            "over_2_5", "under_2_5", "btts", "btts_no",
            "over_1_5", "over_3_5",
        ):
            clv_bias[mkt] = _clv_bias_for_market(db, mkt)

        all_candidates: list[_Candidate] = []
        for ctx in contexts:
            all_candidates.extend(_candidates_from_match(ctx, clv_bias))
        all_candidates.extend(_cross_match_candidates(contexts, clv_bias))

        if not all_candidates:
            return {"status": "no_candidates", "matches_scanned": len(upcoming)}

        finalists = _dedupe(all_candidates)

        # Cross-run idempotency: never re-publish a multi whose exact leg-set is
        # already pending. Without this the 30-min tick duplicates the same picks
        # every run whenever live_pending < cap (observed 2026-07-06: two
        # identical Portugal-v-Spain multis). Also cap total live picks at the
        # daily max by only filling the remaining slots.
        existing_sigs: set[frozenset] = set()
        for mm in db.query(ModelMulti).filter(ModelMulti.status == "pending").all():
            legs = db.query(ModelMultiLeg).filter(ModelMultiLeg.multi_id == mm.id).all()
            existing_sigs.add(frozenset((l.match_id, l.market) for l in legs))
        slots = max(0, MAX_PICKS_PER_DAY - live_pending)

        added = 0
        for cand in finalists:
            if added >= slots:
                break
            sig = frozenset((l["match_id"], l["market"]) for l in cand.leg_specs)
            if sig in existing_sigs:
                continue
            existing_sigs.add(sig)
            fair_odds = 1.0 / cand.combined_prob if cand.combined_prob > 0 else None
            ev_pct = (cand.combined_prob * cand.combined_book_odds - 1.0) * 100
            kelly = quarter_kelly(cand.combined_prob, cand.combined_book_odds)
            mm = ModelMulti(
                generated_at=now,
                label=cand.label,
                kind=cand.kind,
                combined_prob=round(cand.combined_prob, 6),
                combined_fair_odds=round(fair_odds, 3) if fair_odds else None,
                combined_book_odds=round(cand.combined_book_odds, 3),
                ev_pct=round(ev_pct, 2),
                kelly_pct=round(kelly * 100, 2),
                status="pending",
            )
            db.add(mm)
            db.flush()  # need mm.id
            for spec in cand.leg_specs:
                db.add(ModelMultiLeg(
                    multi_id=mm.id,
                    leg_order=spec["leg_order"],
                    match_id=spec["match_id"],
                    market=spec["market"],
                    market_label=spec["market_label"],
                    model_prob=round(spec["model_prob"], 6) if spec["model_prob"] else None,
                    market_implied_prob=round(spec["market_implied_prob"], 6) if spec.get("market_implied_prob") else None,
                    book_odds=spec.get("book_odds"),
                    book_name=spec.get("book_name"),
                ))
            added += 1
        db.commit()
        return {"status": "ok", "added": added, "candidates_considered": len(all_candidates)}
    finally:
        db.close()


# ---- Settlement ----------------------------------------------------------

# Maps a market key to a function (home_score, away_score) -> bool (leg won?)
_SETTLE_FN: dict[str, callable] = {  # type: ignore[type-arg]
    "home_win": lambda h, a: h > a,
    "draw":     lambda h, a: h == a,
    "away_win": lambda h, a: a > h,
    "1x":       lambda h, a: h >= a,
    "x2":       lambda h, a: a >= h,
    "12":       lambda h, a: h != a,
    "btts":     lambda h, a: h > 0 and a > 0,
    "btts_no":  lambda h, a: not (h > 0 and a > 0),
    "over_1_5": lambda h, a: (h + a) >= 2,
    "over_2_5": lambda h, a: (h + a) >= 3,
    "over_3_5": lambda h, a: (h + a) >= 4,
    "under_2_5": lambda h, a: (h + a) <= 2,
    "under_3_5": lambda h, a: (h + a) <= 3,
    "under_4_5": lambda h, a: (h + a) <= 4,
    "home_clean_sheet": lambda h, a: a == 0,
    "away_clean_sheet": lambda h, a: h == 0,
    "goals_1_to_3":     lambda h, a: 1 <= (h + a) <= 3,
    "goals_2_to_4":     lambda h, a: 2 <= (h + a) <= 4,
    "goals_3_to_5":     lambda h, a: 3 <= (h + a) <= 5,
}


def settle_finished_multis() -> dict:
    """Find pending multis whose legs are all complete and settle them.
    Reads home_score/away_score off the Match row (filled by score_refresh).

    Interruption-aware: if ANY leg's match is interrupted (delayed /
    postponed / abandoned / awarded) the WHOLE multi voids per industry
    rule. Mirrors how every major book settles parlays — one voided leg
    short-circuits the parlay's stake-refund. See
    docs/plans/2026-06-23_match-interruption-handling.md §7b for source
    cites (bet365 / Betfair / Sky / Paddy).
    """
    from backend.betting.settlement_rules import pick_voided, pick_settle_able
    summary = {"checked": 0, "settled": 0, "won": 0, "lost": 0, "void": 0}
    db = SessionLocal()
    try:
        pending = db.query(ModelMulti).filter(ModelMulti.status == "pending").all()
        for mm in pending:
            summary["checked"] += 1
            legs = db.query(ModelMultiLeg).filter(ModelMultiLeg.multi_id == mm.id).all()
            # All legs must reference matches that are settle-able or
            # voided — one undecided leg parks the multi for next pass.
            settled_legs = []
            void = False
            for leg in legs:
                m = db.get(Match, leg.match_id)
                # Voided leg -> whole multi voids (parlay short-circuit).
                if pick_voided(m):
                    void = True
                    break
                # Not settle-able and not voided -> wait for next pass.
                if not pick_settle_able(m):
                    settled_legs = None
                    break
                fn = _SETTLE_FN.get(leg.market)
                if not fn:
                    void = True
                    break
                # Bookmaker convention: 1X2/totals/BTTS settle on the 90-minute
                # score. m.home_score holds the reg+ET aggregate for knockouts,
                # so an ET winner would wrongly settle "draw" legs as lost (and
                # ET goals would flip totals). ft_* is the 90' score; fall back
                # to the stored score for group-stage rows predating the column
                # (identical value there — groups can't go to ET).
                h_ref = m.ft_home_score if m.ft_home_score is not None else m.home_score
                a_ref = m.ft_away_score if m.ft_away_score is not None else m.away_score
                settled_legs.append((leg, fn(h_ref, a_ref)))
            if settled_legs is None:
                continue
            if void:
                mm.status = "void"
                mm.settled_at = datetime.utcnow()
                mm.profit_loss_units = 0.0
                summary["void"] += 1
                summary["settled"] += 1
                continue
            won = all(w for _, w in settled_legs)
            for leg, w in settled_legs:
                leg.leg_status = "won" if w else "lost"
                leg.settled_at = datetime.utcnow()
            mm.status = "won" if won else "lost"
            mm.settled_at = datetime.utcnow()
            mm.profit_loss_units = round((mm.combined_book_odds - 1.0), 3) if won else -1.0
            if won:
                summary["won"] += 1
            else:
                summary["lost"] += 1
            summary["settled"] += 1
        db.commit()
        return summary
    finally:
        db.close()
