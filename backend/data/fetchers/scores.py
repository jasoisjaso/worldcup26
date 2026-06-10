"""Fetches completed match scores from The Odds API and writes them to the DB.

Runs every 30 minutes. Costs 2 quota units per call (daysFrom=1).
Only updates matches that are still status='upcoming' — won't overwrite manual patches.
"""
import difflib
import logging
import os

import httpx
from sqlalchemy.orm import aliased

from backend.db.models import Match, Team
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
SPORT_KEY = "soccer_fifa_world_cup"
BASE_URL = "https://api.the-odds-api.com/v4"


def _name_score(api_name: str, db_name: str) -> float:
    a = api_name.lower().strip()
    b = db_name.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


async def refresh_scores() -> None:
    if not ODDS_API_KEY:
        logger.warning("ODDS_API_KEY not set — skipping score refresh")
        return

    url = f"{BASE_URL}/sports/{SPORT_KEY}/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": 1}

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
        except Exception as exc:
            logger.error("Score fetch failed: %s", exc)
            return

    events = resp.json()
    completed = [e for e in events if e.get("completed") and e.get("scores")]
    if not completed:
        return

    db = SessionLocal()
    try:
        HomeTeam = aliased(Team, name="home_team")
        AwayTeam = aliased(Team, name="away_team")
        db_matches = (
            db.query(Match, HomeTeam, AwayTeam)
            .join(HomeTeam, Match.home_code == HomeTeam.code)
            .join(AwayTeam, Match.away_code == AwayTeam.code)
            .filter(Match.status == "upcoming")
            .all()
        )

        updated = 0
        for event in completed:
            api_home = event["home_team"]
            api_away = event["away_team"]
            scores_map = {s["name"]: int(s["score"]) for s in event["scores"]}

            best_match = None
            best_score = 0.0
            for m, home, away in db_matches:
                score = (
                    _name_score(api_home, home.name) + _name_score(api_away, away.name)
                ) / 2
                if score > best_score:
                    best_score = score
                    best_match = (m, home, away)

            if best_match is None or best_score < 0.5:
                logger.debug("No DB match for %s vs %s (score=%.2f)", api_home, api_away, best_score)
                continue

            m, home, away = best_match
            home_score = scores_map.get(api_home, scores_map.get(home.name))
            away_score = scores_map.get(api_away, scores_map.get(away.name))

            if home_score is None or away_score is None:
                logger.warning("Could not resolve scores for %s vs %s: %s", api_home, api_away, scores_map)
                continue

            m.home_score = home_score
            m.away_score = away_score
            m.status = "complete"
            updated += 1
            logger.info("Result: %s %d-%d %s", home.name, home_score, away_score, away.name)

        if updated:
            db.commit()
            logger.info("Score refresh: %d match(es) updated", updated)

    finally:
        db.close()
