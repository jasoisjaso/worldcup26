"""Queue seeders for the harvest pipeline — EXTENDED.

Builds on the original harvester_seed.py with:
- 21 leagues (was 9)
- 15 seasons per league (was 2)
- National team fixtures + players per season
- All new endpoints: lineups, h2h, standings, team stats, coaches, transfers, sidelined, topscorers, topassists

Every seeder enqueues via harvester.enqueue() which deduplicates automatically.
Calling a seeder twice is safe — no double-queuing.

Priority tiers:
    60:   WC player stats
    65:   All club player stats
    70:   WC fixture players
    150:  League fixture list
    160:  Team season stats, H2H pairs
    170:  Standings, topscorers, topassists
    200:  Per-fixture fan-out (stats, events, predictions, players, lineups)
    250:  Coaches, sidelined (lower priority — nice to have)
"""
from __future__ import annotations

from backend.data.harvester import enqueue

# ---- League registry ------------------------------------------------------
# All 21 leagues we harvest. ID verified against live /leagues API 2026-06-21.
LEAGUES = [
    {"id": 39,  "name": "Premier League",         "fixtures": 380},
    {"id": 40,  "name": "Championship",            "fixtures": 552},
    {"id": 78,  "name": "Bundesliga",              "fixtures": 306},
    {"id": 140, "name": "La Liga",                 "fixtures": 380},
    {"id": 135, "name": "Serie A",                 "fixtures": 380},
    {"id": 61,  "name": "Ligue 1",                 "fixtures": 306},
    {"id": 2,   "name": "Champions League",        "fixtures": 125},
    {"id": 88,  "name": "Eredivisie",              "fixtures": 306},
    {"id": 94,  "name": "Primeira Liga",           "fixtures": 306},
    {"id": 71,  "name": "Brasileirao",             "fixtures": 380},
    {"id": 128, "name": "Argentine Liga",          "fixtures": 378},
    {"id": 188, "name": "A-League",                "fixtures": 156},
    {"id": 253, "name": "MLS",                     "fixtures": 510},
    {"id": 262, "name": "Liga MX",                 "fixtures": 306},
    {"id": 203, "name": "Super Lig",               "fixtures": 342},
    {"id": 119, "name": "Eliteserien",             "fixtures": 240},
    {"id": 113, "name": "Danish Superliga",        "fixtures": 192},
    {"id": 218, "name": "Austrian Bundesliga",     "fixtures": 192},
    {"id": 345, "name": "Czech Liga",              "fixtures": 240},
    {"id": 106, "name": "Ekstraklasa",             "fixtures": 306},
    {"id": 283, "name": "Liga I",                  "fixtures": 240},
]

# 15 seasons of data (2010-2024) for major leagues. api-football has data back
# to 2010 for the big 6. For medium leagues (2016+) we fall back gracefully —
# the harvester will 404 or return empty for seasons without data; the dedup
# key prevents wasting quota on empty re-queues.
SEASONS_MAJOR = [2010, 2011, 2012, 2013, 2014, 2015, 2016, 2017, 2018, 2019,
                 2020, 2021, 2022, 2023, 2024]
SEASONS_MEDIUM = [2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024]
# Leagues with data from 2010 (verified against live API)
MAJOR_LEAGUE_IDS = {39, 78, 140, 135, 61, 2, 88, 71, 94}

# ---- Legacy compatibility --------------------------------------------------
SEASONS = [2023, 2024]  # kept for backward compat with old callers


def _seasons_for(league_id: int) -> list[int]:
    return SEASONS_MAJOR if league_id in MAJOR_LEAGUE_IDS else SEASONS_MEDIUM


# ---- WC / National Teams -------------------------------------------------

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


def seed_wc_fixture_players() -> dict:
    """One /fixtures/players call per completed WC fixture."""
    from backend.db.session import SessionLocal
    from backend.db.models import Match, MatchEvent
    from sqlalchemy import distinct

    db = SessionLocal()
    added, skipped = 0, 0
    try:
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


# ---- National Team History ------------------------------------------------

def seed_national_team_fixtures() -> dict:
    """One /fixtures?team=X&season=Y call per national team per season.
    ~100 teams × 5 seasons = ~500 calls. Fan-out by the processor adds
    per-fixture statistics/events/players/lineups/predictions."""
    from backend.data.fetchers.injuries import TEAM_IDS
    # Build reverse mapping: api_id → code for all known national teams
    national_ids = set(TEAM_IDS.values())

    # Also discover all national teams from /teams?country=X calls
    # (run once via the verification script — we store them here)
    EXTRA_NATIONAL_IDS = {
        21, 24, 2383, 19, 1117,  # Denmark, Poland, Chile, Nigeria, Greece
        # More populated from verification call — safe to add as discovered
    }
    national_ids.update(EXTRA_NATIONAL_IDS)

    added, skipped = 0, 0
    for api_id in national_ids:
        for season in [2020, 2021, 2022, 2023, 2024]:
            ok = enqueue(
                endpoint="/fixtures",
                params={"team": api_id, "season": season},
                priority=150,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


# ---- Forward odds capture ---------------------------------------------------
# api-football only serves pre-match odds from ~7 days before kickoff and
# EXPIRES them ~14 days after — there is no deep historical odds backfill on
# this API. The only way to own an odds archive (for CLV densification and
# for training EPL/club models on real market prices) is to capture forward,
# continuously. One /odds?league&season&date job per watched league per day;
# the date param doubles as the dedup key so each day is fetched exactly once.
# Blobs land in HarvestRaw (raw-only for now — see _normalise_odds).
# NOTE: /odds paginates (~10 fixtures/page) and the generic fetcher takes
# page 1 only. Fine for WC knockout days (<=2 fixtures); revisit before EPL
# matchweeks (10 fixtures — borderline) by fanning out per-fixture jobs.
ODDS_WATCH = [
    {"league": 1, "season": 2026},    # FIFA World Cup — active now
    # {"league": 39, "season": 2026},  # EPL — enable when the season starts
]
ODDS_LOOKAHEAD_DAYS = 7


def seed_upcoming_odds() -> dict:
    """Enqueue /odds jobs for each watched league × the next 7 UTC days.

    Idempotent: dedup on (endpoint, params) means re-running daily only adds
    the one genuinely new date per league. ~1 API call/league/day steady state
    against a quota that had 70K+ calls unused today.
    """
    from datetime import datetime as _dt, timedelta as _td
    added, skipped = 0, 0
    today = _dt.utcnow().date()
    for w in ODDS_WATCH:
        for d in range(ODDS_LOOKAHEAD_DAYS):
            day = (today + _td(days=d)).isoformat()
            ok = enqueue(
                endpoint="/odds",
                params={"league": w["league"], "season": w["season"], "date": day},
                priority=150,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


# ---- Club League Seeding --------------------------------------------------

def seed_league_fixtures(league_ids: list[int] | None = None) -> dict:
    """Enqueue /fixtures calls for each league × season combo.
    The processor auto-fans-out per-fixture sub-endpoints."""
    if league_ids is None:
        league_ids = [l["id"] for l in LEAGUES]
    target = [l for l in LEAGUES if l["id"] in league_ids]
    added, skipped = 0, 0
    for league in target:
        for season in _seasons_for(league["id"]):
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
    """All 21 leagues × all available seasons."""
    return seed_league_fixtures(league_ids=[l["id"] for l in LEAGUES])


def seed_full_stack() -> dict:
    """WC player stats + all league fixtures. ~5000 calls."""
    stats = seed_wc_player_stats()
    leagues = seed_all_leagues()
    return {
        "wc_player_stats": stats,
        "league_fixtures": leagues,
        "total_added": stats["added"] + leagues["added"],
    }


# ---- New Endpoint Seeders -------------------------------------------------

def seed_standings() -> dict:
    """One /standings call per league per season. ~150 calls."""
    added, skipped = 0, 0
    for league in LEAGUES:
        for season in _seasons_for(league["id"]):
            ok = enqueue(
                endpoint="/standings",
                params={"league": league["id"], "season": season},
                priority=170,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


def seed_team_statistics() -> dict:
    """Team stats are auto-seeded by the processor when /fixtures responses
    are normalised (one per team per league per season). This seed function
    is a no-op — kept for API backward compatibility."""
    return {"added": 0, "skipped": 0, "note": "auto-seeded from /fixtures processor"}


def seed_coaches() -> dict:
    """Coaches are auto-seeded by the processor when /fixtures responses
    are normalised (one per team discovered)."""
    return {"added": 0, "skipped": 0, "note": "auto-seeded from /fixtures processor"}


def seed_sidelined() -> dict:
    """Sidelined are auto-seeded by the processor when /fixtures responses
    are normalised (one per team discovered)."""
    return {"added": 0, "skipped": 0, "note": "auto-seeded from /fixtures processor"}


def seed_topscorers() -> dict:
    """One /players/topscorers call per league per season."""
    added, skipped = 0, 0
    for league in LEAGUES:
        for season in _seasons_for(league["id"]):
            ok = enqueue(
                endpoint="/players/topscorers",
                params={"league": league["id"], "season": season},
                priority=170,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


def seed_topassists() -> dict:
    """One /players/topassists call per league per season."""
    added, skipped = 0, 0
    for league in LEAGUES:
        for season in _seasons_for(league["id"]):
            ok = enqueue(
                endpoint="/players/topassists",
                params={"league": league["id"], "season": season},
                priority=170,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


def seed_h2h_pairs() -> dict:
    """H2H for every WC team pair + known club pairs.
    Seeded per league — processor fans out to individual team pairs."""
    added, skipped = 0, 0
    # WC teams
    from backend.data.fetchers.injuries import TEAM_IDS
    wc_ids = list(TEAM_IDS.values())
    for i in range(len(wc_ids)):
        for j in range(i + 1, len(wc_ids)):
            ok = enqueue(
                endpoint="/fixtures/h2h",
                params={"h2h": f"{wc_ids[i]}-{wc_ids[j]}"},
                priority=160,
            )
            if ok:
                added += 1
            else:
                skipped += 1
    return {"added": added, "skipped": skipped}


# ---- Heavy Seed — Master Function -----------------------------------------

def seed_heavy() -> dict:
    """Queue everything. Can add 200,000+ jobs. Call manually from admin UI
    or let the auto-heavy-seed scheduled job fire it at 20:00 UTC."""
    results = {}

    # Club leagues — fixture lists (fans out to 5 sub-endpoints)
    results["all_leagues"] = seed_all_leagues()

    # National teams
    results["national_fixtures"] = seed_national_team_fixtures()
    results["wc_fixture_players"] = seed_wc_fixture_players()

    # League-level endpoints
    results["standings"] = seed_standings()
    results["team_stats"] = seed_team_statistics()
    results["topscorers"] = seed_topscorers()
    results["topassists"] = seed_topassists()

    # H2H
    results["h2h"] = seed_h2h_pairs()

    # Lower priority
    results["coaches"] = seed_coaches()
    results["sidelined"] = seed_sidelined()

    total = sum(r.get("added", 0) for r in results.values())
    results["total_jobs_added"] = total
    return results
