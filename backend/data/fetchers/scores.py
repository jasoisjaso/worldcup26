"""Fetches completed match scores and writes them to the DB.

Primary source: football-data.org (FOOTBALL_DATA_KEY) — has WC 2026 data.
Fallback: The Odds API scores endpoint (requires paid tier for scores).
Only updates matches that are still status='upcoming' — won't overwrite manual patches.

The football-data.org "WC" competition returns results across every World Cup
edition, so a historical fixture (e.g. WC 2018 Mexico vs South Korea) would
silently overwrite the matching 2026 fixture if we only matched on team pairing.
Both writers guard with ``m.kickoff <= now`` so a future fixture is never marked
complete.
"""
import difflib
import logging
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy.orm import aliased

from backend.db.models import Match, Team
from backend.db.session import SessionLocal


def _kickoff_passed(m: Match) -> bool:
    """A fixture's kickoff is in the past, so a 'completed' result for the same
    team pairing is plausibly for THIS fixture and not a historical edition."""
    if m.kickoff is None:
        return True  # no kickoff = nothing to guard against
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    return m.kickoff <= now

logger = logging.getLogger(__name__)

ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
FD_KEY = os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALL_DATA_ORG_KEY", "")
SPORT_KEY = "soccer_fifa_world_cup"
BASE_URL = "https://api.the-odds-api.com/v4"
FD_BASE = "https://api.football-data.org/v4"

# football-data.org TLA -> our team code
_FD_TLA_TO_CODE: dict[str, str] = {
    "MEX": "mx", "RSA": "za", "KOR": "kr", "CZE": "cz",
    "CAN": "ca", "BIH": "ba", "USA": "us", "PAR": "py",
    "QAT": "qa", "SUI": "ch", "BRA": "br", "MAR": "ma",
    "HAI": "ht", "SCO": "gb-sct", "AUS": "au", "TUR": "tr",
    "GER": "de", "CUW": "cw", "NED": "nl", "JPN": "jp",
    "SWE": "se", "TUN": "tn", "BEL": "be", "EGY": "eg",
    "IRN": "ir", "NZL": "nz", "ESP": "es", "CPV": "cv",
    "KSA": "sa", "URU": "uy", "FRA": "fr", "SEN": "sn",
    "IRQ": "iq", "NOR": "no", "ARG": "ar", "ALG": "dz",
    "AUT": "at", "JOR": "jo", "POR": "pt", "COD": "cd",
    "COL": "co", "UZB": "uz", "ENG": "gb-eng", "CRO": "hr",
    "GHA": "gh", "CIV": "ci", "ECU": "ec",
}


def _name_score(api_name: str, db_name: str) -> float:
    a = api_name.lower().strip()
    b = db_name.lower().strip()
    if a == b:
        return 1.0
    if a in b or b in a:
        return 0.85
    return difflib.SequenceMatcher(None, a, b).ratio()


async def _fetch_completed_fdorg() -> list[dict]:
    """Return list of {home_code, away_code, home_score, away_score} from football-data.org."""
    if not FD_KEY:
        return []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{FD_BASE}/competitions/WC/matches",
                headers={"X-Auth-Token": FD_KEY},
                params={"status": "FINISHED"},
            )
            if resp.status_code != 200:
                logger.warning("football-data.org scores returned %s", resp.status_code)
                return []
            matches = resp.json().get("matches", [])
    except Exception as exc:
        logger.error("football-data.org score fetch failed: %s", exc)
        return []

    results = []
    for m in matches:
        ht = m.get("homeTeam", {}).get("tla", "")
        at = m.get("awayTeam", {}).get("tla", "")
        ft = m.get("score", {}).get("fullTime", {})
        hc = _FD_TLA_TO_CODE.get(ht)
        ac = _FD_TLA_TO_CODE.get(at)
        if hc and ac and ft.get("home") is not None and ft.get("away") is not None:
            results.append({
                "home_code": hc, "away_code": ac,
                "home_score": int(ft["home"]), "away_score": int(ft["away"]),
            })
    return results


async def _write_scores_from_fdorg(results: list[dict]) -> None:
    db = SessionLocal()
    try:
        upcoming = {
            (m.home_code, m.away_code): m
            for m in db.query(Match).filter(Match.status == "upcoming").all()
        }
        updated = 0
        for r in results:
            m = upcoming.get((r["home_code"], r["away_code"]))
            swapped = False
            if not m:
                # football-data.org may list a fixture with home/away reversed relative
                # to our schedule row. Match the flipped tuple and swap the scores back,
                # mirroring the Odds-API fallback path so the primary source never
                # silently drops a played result.
                m = upcoming.get((r["away_code"], r["home_code"]))
                swapped = True
            if not m:
                continue
            if not _kickoff_passed(m):
                logger.warning(
                    "Skipping fd.org result for %s vs %s — kickoff is in the future "
                    "(%s). Likely a historical World Cup edition.",
                    m.home_code, m.away_code, m.kickoff,
                )
                continue
            if swapped:
                m.home_score = r["away_score"]
                m.away_score = r["home_score"]
            else:
                m.home_score = r["home_score"]
                m.away_score = r["away_score"]
            m.status = "complete"
            updated += 1
            logger.info("Result (fd.org): %s %d-%d %s", m.home_code, m.home_score, m.away_score, m.away_code)
        if updated:
            db.commit()
            from backend.data.fetchers.tournament_form import rebuild as _rebuild_tf
            _rebuild_tf(db)
            logger.info("Score refresh (fd.org): %d match(es) updated", updated)
    finally:
        db.close()


async def refresh_scores() -> None:
    # Try football-data.org first (primary — has WC 2026)
    fd_results = await _fetch_completed_fdorg()
    if fd_results:
        await _write_scores_from_fdorg(fd_results)
        return

    # Fallback: Odds API scores (requires paid tier)
    if not ODDS_API_KEY:
        logger.warning("ODDS_API_KEY not set and football-data.org returned nothing — skipping score refresh")
        return

    url = f"{BASE_URL}/sports/{SPORT_KEY}/scores"
    params = {"apiKey": ODDS_API_KEY, "daysFrom": 3}

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
                h_score = _name_score(api_home, home.name)
                a_score = _name_score(api_away, away.name)
                # Both teams must individually match — prevents one perfect name
                # carrying a wrong opponent over the threshold.
                if h_score < 0.6 or a_score < 0.6:
                    continue
                score = (h_score + a_score) / 2
                if score > best_score:
                    best_score = score
                    best_match = (m, home, away)

            if best_match is None or best_score < 0.7:
                logger.debug("No DB match for %s vs %s (score=%.2f)", api_home, api_away, best_score)
                continue

            m, home, away = best_match
            home_score = scores_map.get(api_home, scores_map.get(home.name))
            away_score = scores_map.get(api_away, scores_map.get(away.name))

            if home_score is None or away_score is None:
                logger.warning("Could not resolve scores for %s vs %s: %s", api_home, api_away, scores_map)
                continue
            if not _kickoff_passed(m):
                logger.warning(
                    "Skipping Odds-API result for %s vs %s — kickoff is in the future "
                    "(%s). Likely a historical World Cup edition.",
                    home.name, away.name, m.kickoff,
                )
                continue

            m.home_score = home_score
            m.away_score = away_score
            m.status = "complete"
            updated += 1
            logger.info("Result: %s %d-%d %s", home.name, home_score, away_score, away.name)

        if updated:
            db.commit()
            from backend.data.fetchers.tournament_form import rebuild as _rebuild_tf
            _rebuild_tf(db)
            logger.info("Score refresh: %d match(es) updated", updated)

    finally:
        db.close()
