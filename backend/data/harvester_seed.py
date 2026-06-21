"""Queue seeders for the harvest pipeline.

Builds on seed_wc_squads() (already in harvester.py) with league-level
seeding. Every seeder enqueues via harvester.enqueue() which deduplicates
automatically — calling a seeder twice is safe, no double-queuing.

Leagues + season coverage:

    Prem (39), Bundesliga (78), La Liga (140), Serie A (135), Ligue 1 (61).
    Seasons 2023 and 2024 (2025 hasn't started for most leagues yet).

Priority tiers:
    50:   WC squads (existing)
    60:   WC player stats per season
    150:  League fixture list
    200:  Per-fixture fan-out (stats, events, predictions, odds)

Do NOT leak these IDs or counts in public commit messages or docs.
"""
from __future__ import annotations

from backend.data.harvester import enqueue

# League IDs from api-football v3 coverage.
LEAGUES = [
    {"id": 39,  "name": "Premier League",   "fixtures": 380},
    {"id": 78,  "name": "Bundesliga",        "fixtures": 306},
    {"id": 140, "name": "La Liga",           "fixtures": 380},
    {"id": 135, "name": "Serie A",           "fixtures": 380},
    {"id": 61,  "name": "Ligue 1",           "fixtures": 306},
    {"id": 2,   "name": "Champions League",  "fixtures": 125},
    {"id": 88,  "name": "Eredivisie",        "fixtures": 306},
    {"id": 71,  "name": "Brasileirao",       "fixtures": 380},
    {"id": 188, "name": "A-League",          "fixtures": 156},
]

SEASONS = [2023, 2024]


def seed_wc_player_stats() -> dict:
    """One job per WC team per season for player season stats.
    ~48 teams × 2 seasons = 96 calls."""
    from backend.data.fetchers.injuries import TEAM_IDS
    added, skipped = 0, 0
    for season in SEASONS:
        for _code, api_id in TEAM_IDS.items():
            ok = enqueue(
                endpoint="/players",
                params={"team": api_id, "season": season},
                priority=60,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


def seed_league_fixtures(league_ids: list[int] | None = None) -> dict:
    """Enqueue /fixtures calls for each league × season combo.
    The processor will auto-fan-out per-fixture sub-endpoints when it
    encounters each response.

    Pass league_ids to restrict (e.g. [39, 78] for EPL + Bundesliga only).
    Default: EPL + Bundesliga (the two the owner named)."""
    if league_ids is None:
        league_ids = [39, 78]
    target_leagues = [l for l in LEAGUES if l["id"] in league_ids]
    added, skipped = 0, 0
    for league in target_leagues:
        for season in SEASONS:
            ok = enqueue(
                endpoint="/fixtures",
                params={"league": league["id"], "season": season},
                priority=150,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


def seed_all_leagues() -> dict:
    """Enqueue /fixtures for all 9 leagues × 2 seasons."""
    return seed_league_fixtures(league_ids=[l["id"] for l in LEAGUES])


def seed_full_stack() -> dict:
    """Add WC player stats + EPL/Bundesliga fixtures. Safe to call on every
    startup — dedup prevents re-queuing. ~160 calls added to the queue."""
    stats = seed_wc_player_stats()
    leagues = seed_league_fixtures()
    return {
        "wc_player_stats": stats,
        "league_fixtures": leagues,
        "total_added": stats["added"] + leagues["added"],
    }


def seed_wc_fixture_players() -> dict:
    """One /fixtures/players call per completed WC fixture we have an
    api_fixture_id for (via MatchEvent). Feeds PlayerHistory + the goalscorer
    market. ~36 calls today, grows as the tournament progresses.

    Priority 70 — higher than the league-fixture fan-out (250) so WC data
    fills first when the harvester drains the queue.
    """
    # Imports local so the seeder module stays cheap to import in non-DB
    # contexts (e.g. testing the seeder's enqueue path on its own).
    from backend.db.session import SessionLocal
    from backend.db.models import Match, MatchEvent
    from sqlalchemy import distinct

    db = SessionLocal()
    added, skipped = 0, 0
    try:
        # Distinct api_fixture_ids on completed matches. MatchEvent is the
        # only place we record the api-football fixture id for WC matches
        # (Match has only our internal "M001" codes).
        rows = (
            db.query(distinct(MatchEvent.api_fixture_id))
            .join(Match, Match.id == MatchEvent.match_id)
            .filter(Match.status == "complete")
            .filter(MatchEvent.api_fixture_id.isnot(None))
            .all()
        )
        for (fid,) in rows:
            if not fid:
                continue
            ok = enqueue(
                endpoint="/fixtures/players",
                params={"fixture": int(fid)},
                priority=70,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    finally:
        db.close()
    return {"added": added, "skipped_already_queued": skipped}
