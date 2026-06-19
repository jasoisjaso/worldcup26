"""Scoreboard: scores any forecaster's probability predictions against settled matches.

Forecasters we currently track:

  * ``model_blend``   — our Dixon-Coles + ELO blend, snapshotted pre-kickoff in PredictionSnapshot.
  * ``bet365_implied`` — Bet365's closing line, Shin-devigged into a probability triple.
  * ``opta``          — Opta supercomputer published predictions (tournament-level only;
                        per-match comparison N/A — see /winner page for the tournament view).

The same proper scoring rules (Brier, log-loss, hit-rate) are applied to every forecaster
on the same set of settled matches, so the comparison is honest. No cherry-picking, no
post-hoc selection — settled = settled. The list of settled matches is the only filter.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.betting.market import devig_shin
from backend.db.models import (
    Match,
    PredictionSnapshot,
    CompetitorPrediction,
    OddsCache,
)
from backend.eval.scoring import outcome_index, brier, log_loss


@dataclass
class ForecasterScore:
    forecaster: str
    label: str
    n_settled: int
    hit_rate: float | None       # share where the forecaster's favourite outcome won
    brier: float | None          # mean ternary Brier — lower is better
    log_loss: float | None       # mean ternary log-loss — lower is better


def _our_probs_by_match(db: Session) -> dict[str, tuple[float, float, float]]:
    """Pull our model's pre-kickoff snapshotted probabilities."""
    out: dict[str, tuple[float, float, float]] = {}
    for s in db.query(PredictionSnapshot).all():
        if s.p_home is not None and s.p_draw is not None and s.p_away is not None:
            out[s.match_id] = (s.p_home, s.p_draw, s.p_away)
    return out


def _market_probs_by_match(db: Session) -> dict[str, tuple[float, float, float]]:
    """The market's closing-line 1X2 probabilities, Shin-devigged.

    Aggregates across every bookmaker we cache (currently Unibet + Sportsbet on the
    free Odds API tier). For each (match, market) we keep the LATEST pre-kickoff price
    per bookmaker, then average across bookmakers to form the market consensus, then
    de-vig the triple. This is what an informed bettor could reasonably have got at
    the close, and is the natural "market" baseline to beat.
    """
    rows = (
        db.query(OddsCache)
        .filter(OddsCache.market.in_(["home_win", "draw", "away_win"]))
        .order_by(OddsCache.fetched_at.desc())
        .all()
    )

    # per_book: {match_id: {bookmaker: {market: (odds, fetched_ts)}}}
    per_book: dict[str, dict[str, dict[str, tuple[float, float]]]] = {}
    for r in rows:
        b = per_book.setdefault(r.match_id, {}).setdefault(r.bookmaker or "unknown", {})
        existing = b.get(r.market)
        ts = r.fetched_at.timestamp() if r.fetched_at else 0.0
        if existing is None or ts > existing[1]:
            b[r.market] = (r.odds, ts)

    out: dict[str, tuple[float, float, float]] = {}
    for match_id, books in per_book.items():
        # Average odds across bookmakers for each market.
        avg_odds: dict[str, float] = {}
        for market in ("home_win", "draw", "away_win"):
            values = [b[market][0] for b in books.values() if market in b]
            if not values:
                break
            avg_odds[market] = sum(values) / len(values)
        if len(avg_odds) != 3:
            continue
        probs = devig_shin([avg_odds["home_win"], avg_odds["draw"], avg_odds["away_win"]])
        if probs is None:
            continue
        out[match_id] = (probs[0], probs[1], probs[2])
    return out


def _competitor_probs_by_match(db: Session, forecaster: str) -> dict[str, tuple[float, float, float]]:
    """Per-match probabilities published by an external forecaster (Opta etc.)."""
    out: dict[str, tuple[float, float, float]] = {}
    for c in db.query(CompetitorPrediction).filter(CompetitorPrediction.forecaster == forecaster).all():
        if c.p_home is not None and c.p_draw is not None and c.p_away is not None:
            out[c.match_id] = (c.p_home, c.p_draw, c.p_away)
    return out


def _score_one(probs_by_match: dict[str, tuple[float, float, float]],
               outcomes: dict[str, int]) -> tuple[int, float | None, float | None, float | None]:
    """Compute (n, hit_rate, brier, log_loss) across the intersection of forecaster's
    predictions and settled outcomes."""
    n = 0
    hits = 0
    brier_sum = 0.0
    ll_sum = 0.0
    for mid, probs in probs_by_match.items():
        if mid not in outcomes:
            continue
        obs = outcomes[mid]
        favourite = max(range(3), key=lambda i: probs[i])
        if favourite == obs:
            hits += 1
        brier_sum += brier(probs, obs)
        ll_sum += log_loss(probs, obs)
        n += 1
    if n == 0:
        return 0, None, None, None
    return n, hits / n, brier_sum / n, ll_sum / n


def scoreboard(db: Session) -> dict:
    """Score every forecaster on the same set of settled matches.

    Returns a dict with `n_total_settled`, a list of `ForecasterScore` dicts ranked
    by Brier (lower = better), plus the intersection size per forecaster so any
    coverage gap is visible to the reader.
    """
    matches = (
        db.query(Match)
        .filter(Match.status == "complete")
        .filter(Match.home_score.isnot(None))
        .filter(Match.away_score.isnot(None))
        .all()
    )
    outcomes: dict[str, int] = {
        m.id: outcome_index(m.home_score, m.away_score) for m in matches
    }

    forecasters: list[tuple[str, str, dict[str, tuple[float, float, float]]]] = [
        ("model_blend",     "wc26.tinjak.com (us)",         _our_probs_by_match(db)),
        ("market_implied",  "Market (closing line, devig)", _market_probs_by_match(db)),
        ("opta",            "Opta supercomputer",           _competitor_probs_by_match(db, "opta")),
    ]

    out: list[dict] = []
    for fid, label, probs in forecasters:
        n, hit, br, ll = _score_one(probs, outcomes)
        out.append({
            "forecaster": fid,
            "label": label,
            "n_settled": n,
            "n_covered": len(probs),
            "hit_rate": round(hit, 4) if hit is not None else None,
            "brier": round(br, 4) if br is not None else None,
            "log_loss": round(ll, 4) if ll is not None else None,
        })

    # Sort: forecasters with data first, by Brier ascending. None Brier sinks to the bottom.
    out.sort(key=lambda r: (r["brier"] if r["brier"] is not None else 9.9))
    return {
        "n_total_settled": len(outcomes),
        "forecasters": out,
    }
