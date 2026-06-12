"""Auto-logs positive-EV predictions for each match before kickoff.

Pick criteria (all must pass):
  - EV >= 4%  (not just any positive EV — eliminates noise from model miscalibration)
  - Model probability >= floor per market  (no longshot logging below 20%)
  - Quarter-Kelly fraction >= 2%  (mathematically eliminates tiny-edge, high-variance bets)
  - Logged within 12h of kickoff  (odds are settled by then; 48h odds are still moving)
  - Blended probability used for EV  (matches what the UI shows — 70% model / 30% vig-removed market)
"""
from datetime import datetime, timedelta

from backend.db.session import SessionLocal
from backend.db.models import Match, Team, Prediction, PredictionSnapshot
from backend.models.group_predictor import predict_group_match
from backend.models.prediction_inputs import assemble
from backend.betting.ev import calculate_ev
from backend.betting.kelly import quarter_kelly
from backend.betting.market import blend_three_way, blend_two_way
from backend.data.fetchers.odds import get_odds_for_match
from backend.version import MODEL_VERSION

# Log picks in the 12-hour window before kickoff only (odds are settled by then)
WINDOW_HOURS = 12

# Minimum edge — filters out noise and model miscalibration
MIN_EV = 0.04

# Minimum quarter-Kelly fraction — naturally eliminates low-prob / tiny-edge combos
MIN_KELLY = 0.02

# Minimum model probability per market — no logging on extreme longshots
_MIN_PROB: dict[str, float] = {
    "home_win": 0.20,
    "draw":     0.20,
    "away_win": 0.20,
    "over_2_5": 0.38,
    "btts":     0.38,
}


def _upsert_snapshot(db, match_id, p_home, p_draw, p_away, p_over, p_btts, lam_h, lam_a):
    """Keep one current pre-kickoff snapshot per match (latest estimate wins)."""
    snap = db.query(PredictionSnapshot).filter(PredictionSnapshot.match_id == match_id).first()
    if snap is None:
        snap = PredictionSnapshot(match_id=match_id)
        db.add(snap)
    snap.model_version = MODEL_VERSION
    snap.p_home, snap.p_draw, snap.p_away = p_home, p_draw, p_away
    snap.p_over_2_5, snap.p_btts = p_over, p_btts
    snap.lambda_home, snap.lambda_away = lam_h, lam_a
    snap.logged_at = datetime.utcnow()


async def log_upcoming_predictions() -> None:
    now = datetime.utcnow()
    window_end = now + timedelta(hours=WINDOW_HOURS)

    db = SessionLocal()
    try:
        upcoming = (
            db.query(Match)
            .filter(
                Match.status == "upcoming",
                Match.kickoff >= now,
                Match.kickoff <= window_end,
            )
            .all()
        )

        logged_count = 0
        for m in upcoming:
            already_markets = {
                p.market
                for p in db.query(Prediction).filter(Prediction.match_id == m.id).all()
            }

            home = db.get(Team, m.home_code)
            away = db.get(Team, m.away_code)
            if not home or not away:
                continue

            # Full model — identical assembly to the live route.
            ctx = await assemble(m, home, away, db)
            pred = predict_group_match(
                ctx["home_input"], ctx["away_input"],
                venue_context=ctx["venue_context"], matchday=m.matchday,
                **ctx["modifiers"],
            )

            live_odds = await get_odds_for_match(m.id)

            # Blend with Shin-devigged market, same as the UI route. The blend helpers
            # return the raw model probability unchanged when no usable odds are present.
            h_prob, d_prob, a_prob = blend_three_way(
                pred.home_win, pred.draw, pred.away_win, live_odds
            )
            over_prob, _under = blend_two_way(
                pred.over_2_5, pred.under_2_5,
                (live_odds or {}).get("over_2_5"), (live_odds or {}).get("under_2_5"),
            )

            # Snapshot the full distribution for EVERY upcoming match (independent of EV
            # selection) so live calibration is measured without selection bias.
            _upsert_snapshot(db, m.id, h_prob, d_prob, a_prob, over_prob, pred.btts,
                             pred.lambda_home, pred.lambda_away)

            if not live_odds:
                # No settled odds yet — snapshot saved; pick logging waits for odds.
                continue

            # Picks/EV use the model's RAW opinion vs the bookie line (the snapshot above
            # keeps the calibrated blend for tracking). This is the "model's own edge"
            # value mode: we bet where the model genuinely disagrees with the bookie.
            market_probs = {
                "home_win": pred.home_win,
                "draw":     pred.draw,
                "away_win": pred.away_win,
                "over_2_5": pred.over_2_5,
                "btts":     pred.btts,
            }

            _RESULT_MARKETS = {"home_win", "draw", "away_win"}
            best_result: tuple | None = None  # (ev, market, prob, odds)

            for market, prob in market_probs.items():
                if market in already_markets:
                    continue
                odds = live_odds.get(market)
                if odds is None:
                    continue

                if prob < _MIN_PROB.get(market, 0.20):
                    continue

                ev = calculate_ev(prob, odds)

                if ev < MIN_EV:
                    continue

                if quarter_kelly(prob, odds) < MIN_KELLY:
                    continue

                if market in _RESULT_MARKETS:
                    # Only keep the single best result-market pick per match
                    if best_result is None or ev > best_result[0]:
                        best_result = (ev, market, prob, odds)
                else:
                    db.add(Prediction(
                        match_id=m.id,
                        market=market,
                        our_probability=prob,
                        bookmaker_odds=odds,
                        ev=ev,
                    ))
                    logged_count += 1

            if best_result and best_result[1] not in already_markets:
                _, market, prob, odds = best_result
                db.add(Prediction(
                    match_id=m.id,
                    market=market,
                    our_probability=prob,
                    bookmaker_odds=odds,
                    ev=calculate_ev(prob, odds),
                ))
                logged_count += 1

        db.commit()
        print(f"[prediction_logger] done — {len(upcoming)} match(es) in window, {logged_count} pick(s) logged")
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(log_upcoming_predictions())
