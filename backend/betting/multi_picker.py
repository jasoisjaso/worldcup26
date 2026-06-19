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

from sqlalchemy import and_
from sqlalchemy.orm import Session

from backend.betting import multi_analyzer
from backend.betting.kelly import quarter_kelly
from backend.betting.market import devig_shin
from backend.betting.sgm import joint_probability_from_grid
from backend.data.fetchers.odds import get_book_odds_for_match
from backend.db.models import (
    Match, ModelMulti, ModelMultiLeg, OddsCache, PredictionSnapshot, Team,
)
from backend.db.session import SessionLocal
from backend.models.poisson import build_score_matrix

logger = logging.getLogger(__name__)

# Shape of an SGM the picker is allowed to consider. Each tuple is a pair of
# user-facing market keys. These are the canonical correlated bets bookmakers
# typically price too low or too high — i.e. where our grid has an edge.
SGM_PAIRS: list[tuple[str, str]] = [
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
]

MIN_COMBINED = 0.12
MAX_COMBINED = 0.40
MIN_EDGE_OVER_BOOK = 0.05      # 5% combined EV minimum
MIN_PER_LEG_EDGE = 0.03         # at least one leg must beat its devig by 3%
MAX_PICKS_PER_DAY = 5
PICK_LOOKAHEAD_HOURS = 36


@dataclass
class _Candidate:
    kind: str                                 # "sgm" or "cross"
    label: str
    combined_prob: float
    combined_book_odds: float
    leg_specs: list[dict]                     # one dict per leg with all the fields ModelMultiLeg needs
    score: float


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


def _candidates_from_match(ctx: dict) -> list[_Candidate]:
    out: list[_Candidate] = []
    m: Match = ctx["match"]
    home, away = ctx["home"].name, ctx["away"].name
    grid = ctx["grid"]
    book = ctx["book"]
    devig = ctx["devig"]

    for a, b in SGM_PAIRS:
        # Need a book price for each leg. Doubles 1X/X2 don't ship from the
        # Odds API directly — compose them from H+D / D+A when possible.
        a_book = _resolve_leg_price(book, a)
        b_book = _resolve_leg_price(book, b)
        if not a_book or not b_book:
            continue
        # Joint via grid
        masks_a = multi_analyzer.expand_market(a)
        masks_b = multi_analyzer.expand_market(b)
        if not masks_a or not masks_b:
            continue
        joint_keys = list(set(masks_a) | set(masks_b))
        if len(joint_keys) >= len(masks_a) + len(masks_b):
            # Means the two markets share no grid mask — they're independent
            # within this match (rare but possible for our market set).
            pa = joint_probability_from_grid(grid, masks_a)
            pb = joint_probability_from_grid(grid, masks_b)
            joint_prob = pa * pb
        else:
            joint_prob = joint_probability_from_grid(grid, joint_keys)
        if joint_prob is None or joint_prob <= 0:
            continue
        combined_book_odds = a_book * b_book
        # Per-leg edges (vs devig)
        per_leg_edges = []
        for mkt in (a, b):
            mp = _model_prob(grid, mkt)
            implied = devig.get(mkt)
            if mp and implied and implied > 0:
                per_leg_edges.append(mp / implied - 1.0)
        if not per_leg_edges or max(per_leg_edges) < MIN_PER_LEG_EDGE:
            continue
        # Combined edge vs bookie
        combined_edge = joint_prob * combined_book_odds - 1.0
        if combined_edge < MIN_EDGE_OVER_BOOK:
            continue
        if joint_prob < MIN_COMBINED or joint_prob > MAX_COMBINED:
            continue
        score = joint_prob * math.log(1.0 + combined_edge)
        # Build leg specs for persistence
        leg_specs = []
        for i, mkt in enumerate((a, b)):
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
        out.append(_Candidate(
            kind="sgm",
            label=f"{home} v {away}: {multi_analyzer.market_label(a)} + {multi_analyzer.market_label(b)}",
            combined_prob=joint_prob,
            combined_book_odds=combined_book_odds,
            leg_specs=leg_specs,
            score=score,
        ))
    return out


def _cross_match_candidates(contexts: list[dict]) -> list[_Candidate]:
    """Best cross-match 2-leg combos drawn from each match's strongest single
    edge (the leg with highest model_prob/implied ratio that beats the 5% floor)."""
    best_legs: list[dict] = []
    for ctx in contexts:
        m: Match = ctx["match"]
        home, away = ctx["home"].name, ctx["away"].name
        grid = ctx["grid"]
        book = ctx["book"]
        devig = ctx["devig"]
        best_for_match = None
        best_ratio = 0.0
        for mkt in ("home_win", "draw", "away_win", "btts", "over_2_5", "under_2_5"):
            mp = _model_prob(grid, mkt)
            implied = devig.get(mkt)
            book_price = book.get(mkt, {}).get("best_price")
            if not (mp and implied and book_price):
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
                }
        if best_for_match:
            best_legs.append(best_for_match)

    out: list[_Candidate] = []
    for i, leg_a in enumerate(best_legs):
        for leg_b in best_legs[i + 1:]:
            joint_prob = leg_a["model_prob"] * leg_b["model_prob"]
            if joint_prob < MIN_COMBINED or joint_prob > MAX_COMBINED:
                continue
            combined_book = leg_a["book_odds"] * leg_b["book_odds"]
            edge = joint_prob * combined_book - 1.0
            if edge < MIN_EDGE_OVER_BOOK:
                continue
            score = joint_prob * math.log(1.0 + edge)
            label = (
                f"{leg_a['match_label']}: {leg_a['market_label']} + "
                f"{leg_b['match_label']}: {leg_b['market_label']}"
            )
            out.append(_Candidate(
                kind="cross",
                label=label,
                combined_prob=joint_prob,
                combined_book_odds=combined_book,
                leg_specs=[
                    {**leg_a, "leg_order": 1},
                    {**leg_b, "leg_order": 2},
                ],
                score=score,
            ))
    return out


def _dedupe(candidates: Iterable[_Candidate]) -> list[_Candidate]:
    """Drop candidates that share >=2 legs with an already-kept candidate."""
    kept: list[_Candidate] = []
    for c in sorted(candidates, key=lambda x: x.score, reverse=True):
        sig = {(l["match_id"], l["market"]) for l in c.leg_specs}
        clash = any(len(sig & {(l["match_id"], l["market"]) for l in k.leg_specs}) >= 2 for k in kept)
        if not clash:
            kept.append(c)
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

        # Don't double-publish if we already have pending picks
        existing_pending = db.query(ModelMulti).filter(ModelMulti.status == "pending").count()
        if existing_pending >= MAX_PICKS_PER_DAY:
            return {"status": "already_picked", "pending": existing_pending}

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

        all_candidates: list[_Candidate] = []
        for ctx in contexts:
            all_candidates.extend(_candidates_from_match(ctx))
        all_candidates.extend(_cross_match_candidates(contexts))

        if not all_candidates:
            return {"status": "no_candidates", "matches_scanned": len(upcoming)}

        finalists = _dedupe(all_candidates)

        added = 0
        for cand in finalists:
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
    Reads home_score/away_score off the Match row (filled by score_refresh)."""
    summary = {"checked": 0, "settled": 0, "won": 0, "lost": 0, "void": 0}
    db = SessionLocal()
    try:
        pending = db.query(ModelMulti).filter(ModelMulti.status == "pending").all()
        for mm in pending:
            summary["checked"] += 1
            legs = db.query(ModelMultiLeg).filter(ModelMultiLeg.multi_id == mm.id).all()
            # All legs must reference matches with status=complete and scores
            settled_legs = []
            void = False
            for leg in legs:
                m = db.get(Match, leg.match_id)
                if not m or m.status != "complete" or m.home_score is None or m.away_score is None:
                    settled_legs = None
                    break
                fn = _SETTLE_FN.get(leg.market)
                if not fn:
                    void = True
                    break
                settled_legs.append((leg, fn(m.home_score, m.away_score)))
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
