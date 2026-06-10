"""Auto-logs the top positive-EV prediction for each match ~2 hours before kickoff."""
from datetime import datetime, timedelta

from backend.db.session import SessionLocal
from backend.db.models import Match, Team, Prediction
from backend.models.group_predictor import predict_group_match, TeamInput
from backend.betting.ev import calculate_ev
from backend.data.fetchers.results import get_recent_form
from backend.data.fetchers.odds import get_odds_for_match

DEFAULT_ODDS = {
    "home_win": 2.00,
    "draw": 3.30,
    "away_win": 3.80,
    "over_2_5": 1.90,
    "btts": 1.85,
}

WINDOW_HOURS = 2


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

        for m in upcoming:
            already = (
                db.query(Prediction)
                .filter(Prediction.match_id == m.id)
                .first()
            )
            if already:
                continue

            home = db.get(Team, m.home_code)
            away = db.get(Team, m.away_code)
            if not home or not away:
                continue

            home_form = await get_recent_form(home.code)
            away_form = await get_recent_form(away.code)

            pred = predict_group_match(
                TeamInput(elo=home.elo or 1500.0, form=home_form, chance_quality=1.3),
                TeamInput(elo=away.elo or 1500.0, form=away_form, chance_quality=1.3),
            )

            live_odds = await get_odds_for_match(m.id)

            market_probs = {
                "home_win": pred.home_win,
                "draw": pred.draw,
                "away_win": pred.away_win,
                "over_2_5": pred.over_2_5,
                "btts": pred.btts,
            }

            best_ev = -1.0
            best_market = None
            for market, prob in market_probs.items():
                odds = live_odds.get(market)
                if odds is None:
                    continue  # only log when backed by live bookmaker odds
                ev = calculate_ev(prob, odds)
                if ev > best_ev:
                    best_ev = ev
                    best_market = market

            if best_market and best_ev > 0:
                odds = live_odds.get(best_market)
                db.add(Prediction(
                    match_id=m.id,
                    market=best_market,
                    our_probability=market_probs[best_market],
                    bookmaker_odds=odds,
                    ev=best_ev,
                ))

        db.commit()
    finally:
        db.close()
