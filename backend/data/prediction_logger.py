"""Auto-logs all positive-EV predictions for each match ~2 hours before kickoff."""
from datetime import datetime, timedelta

from backend.db.session import SessionLocal
from backend.db.models import Match, Team, Prediction
from backend.models.group_predictor import predict_group_match, TeamInput
from backend.models.venue_advantage import get_venue_bonuses
from backend.betting.ev import calculate_ev
from backend.data.fetchers.results import get_recent_form
from backend.data.fetchers.odds import get_odds_for_match

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
            already_markets = {
                p.market
                for p in db.query(Prediction).filter(Prediction.match_id == m.id).all()
            }

            home = db.get(Team, m.home_code)
            away = db.get(Team, m.away_code)
            if not home or not away:
                continue

            home_form = await get_recent_form(home.code)
            away_form = await get_recent_form(away.code)

            venue_home_bonus, venue_away_bonus = get_venue_bonuses(
                home.code, away.code, m.venue or ""
            )

            pred = predict_group_match(
                TeamInput(
                    elo=(home.elo or 1500.0) + venue_home_bonus,
                    form=home_form,
                    chance_quality=1.3,
                    code=home.code,
                ),
                TeamInput(
                    elo=(away.elo or 1500.0) + venue_away_bonus,
                    form=away_form,
                    chance_quality=1.3,
                    code=away.code,
                ),
            )

            live_odds = await get_odds_for_match(m.id)

            market_probs = {
                "home_win": pred.home_win,
                "draw": pred.draw,
                "away_win": pred.away_win,
                "over_2_5": pred.over_2_5,
                "btts": pred.btts,
            }

            for market, prob in market_probs.items():
                if market in already_markets:
                    continue
                odds = live_odds.get(market)
                if odds is None:
                    continue
                ev = calculate_ev(prob, odds)
                if ev > 0:
                    db.add(Prediction(
                        match_id=m.id,
                        market=market,
                        our_probability=prob,
                        bookmaker_odds=odds,
                        ev=ev,
                    ))

        db.commit()
    finally:
        db.close()
