"""Auto-logs positive-EV predictions for each match before kickoff.

Pick criteria (all must pass):
  - EV >= 4%  (not just any positive EV — eliminates noise from model miscalibration)
  - Model probability >= floor per market  (no longshot logging below 20%)
  - Quarter-Kelly fraction >= 2%  (mathematically eliminates tiny-edge, high-variance bets)
  - Logged within 12h of kickoff  (odds are settled by then; 48h odds are still moving)
  - RAW model probability used for EV/pick selection (the model's own edge vs the bookie
    line); the calibrated 70/30 model/market blend is kept only in the PredictionSnapshot
    for unbiased calibration tracking.
"""
from datetime import datetime, timedelta

from backend.db.session import SessionLocal
from backend.db.models import Match, Team, Prediction, PredictionSnapshot
from backend.models.group_predictor import predict_group_match
from backend.models.prediction_inputs import assemble
from backend.betting.ev import calculate_ev
from backend.betting.kelly import quarter_kelly
from backend.betting.market import blend_three_way, blend_two_way, reliability_tier
from backend.data.fetchers.sharp_odds import sharp_anchor_for as _sharp_anchor_for
from backend.data.fetchers.odds import get_odds_for_match
from backend.api.routes.push import send_push
from backend.version import MODEL_VERSION


_MARKET_LABEL = {
    "home_win": "win",
    "draw":     "to draw",
    "away_win": "win",
    "over_2_5": "Over 2.5 goals",
    "btts":     "Both teams to score",
}


def _push_for_pick(db, match: Match, home: Team, away: Team, market: str, prob: float, odds: float, ev: float) -> None:
    """Fire a notification for a newly-found value pick. Dedups by (match, market) so a
    given pick only ever notifies once even if the logger runs many times."""
    label = _MARKET_LABEL.get(market, market)
    if market == "home_win":
        side = home.name
        title = f"Value pick: {home.name}"
    elif market == "away_win":
        side = away.name
        title = f"Value pick: {away.name}"
    elif market == "draw":
        side = "Draw"
        title = f"Value pick: {home.name} v {away.name} draw"
    else:
        side = label
        title = f"Value pick: {home.name} v {away.name}"

    body = f"{side} {label} @ {odds:.2f} · edge +{ev*100:.1f}% · {prob*100:.0f}% model"
    try:
        send_push(
            db,
            title=title,
            body=body,
            url=f"/match/{match.id}",
            dedup_key=f"pick:{match.id}:{market}",
        )
    except Exception as exc:  # never let push break the logger
        print(f"[push] send failed for {match.id}/{market}: {exc}")

# Log picks for matches kicking off within this window. Wide enough that the track record
# fills in a day or two ahead (a 12h window only logged ~2 matches at a time); odds for WC
# group games are stable this far out.
WINDOW_HOURS = 48

# Per-market minimum edge. The flat 4% threshold treated efficient and soft
# markets identically — wasteful on the soft ones (correct-score, HT-FT,
# team-totals: bookmakers don't put their best traders here, 2% can be real
# value), reckless on the efficient ones (1X2 and main O/U: tightest market,
# noise alone can spike 4% without a real edge). Cross-sport literature
# (Levitt 2004 on point-spreads, Štrumbelj 2014 on football odds) puts the
# soft-market spread at ~2-3% and the marquee-line spread at ~5-6%. Defaults
# below land conservatively inside those bounds; raise individual markets if
# settled-results show a calibration problem there.
_MIN_EV_BY_MARKET: dict[str, float] = {
    # Efficient marquee markets — every recreational book has these tight.
    "home_win": 0.05,
    "draw":     0.05,
    "away_win": 0.05,
    "over_2_5": 0.05,
    "under_2_5": 0.05,
    "btts":      0.05,
    "btts_no":   0.05,
    # Softer derivatives — bookmakers price these off the main line, slop is wider.
    "double_chance_1x": 0.03,
    "double_chance_x2": 0.03,
    "double_chance_12": 0.03,
    "team_over_0_5":    0.03,
    "team_over_1_5":    0.03,
    "team_over_2_5":    0.03,
    # Long-tail / soft markets — wide bookmaker margins, real edges show smaller.
    "correct_score":  0.025,
    "ht_ft":          0.025,
    "ht_result":      0.03,
    "exact_goals":    0.025,
    "odd_goals":      0.03,
    "even_goals":     0.03,
}
# Fallback for any market not listed above — conservative middle of the road.
MIN_EV = 0.04


def _min_ev_for(market: str) -> float:
    return _MIN_EV_BY_MARKET.get(market, MIN_EV)

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
            # Sharp anchor (Pinnacle) — see the same logic in predictions.py.
            # When present, becomes the de-vig source; otherwise the soft books
            # below carry the blend on their own.
            sharp = _sharp_anchor_for(home.name, away.name)

            # Blend with Shin-devigged market, same as the UI route. The blend helpers
            # return the raw model probability unchanged when no usable odds are present.
            h_prob, d_prob, a_prob = blend_three_way(
                pred.home_win, pred.draw, pred.away_win, live_odds,
                sharp_anchor=sharp,
            )
            over_prob, _under = blend_two_way(
                pred.over_2_5, pred.under_2_5,
                (live_odds or {}).get("over_2_5"), (live_odds or {}).get("under_2_5"),
                sharp_over=sharp.get("over_2_5") if sharp else None,
                sharp_under=sharp.get("under_2_5") if sharp else None,
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

                # Same guardrail as the value board: don't log longshot fantasies (model
                # straying implausibly far above the bookie) into the track record.
                if reliability_tier(prob, odds) == "longshot":
                    continue

                ev = calculate_ev(prob, odds)

                if ev < _min_ev_for(market):
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
                    _push_for_pick(db, m, home, away, market, prob, odds, ev)

            if best_result and best_result[1] not in already_markets:
                ev_best, market, prob, odds = best_result
                db.add(Prediction(
                    match_id=m.id,
                    market=market,
                    our_probability=prob,
                    bookmaker_odds=odds,
                    ev=ev_best,
                ))
                logged_count += 1
                _push_for_pick(db, m, home, away, market, prob, odds, ev_best)

        db.commit()
        print(f"[prediction_logger] done — {len(upcoming)} match(es) in window, {logged_count} pick(s) logged")
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(log_upcoming_predictions())
