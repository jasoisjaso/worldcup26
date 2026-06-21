# Sentry: ALWAYS call init() at process boot — even with an empty DSN. The
# sentry-sdk asyncio + threading integrations auto-install at import time
# (something in the test stack imports sentry_sdk indirectly), and their
# loop-factory wrapper raises "Sentry init must be called before any other
# imports" the first time TestClient or APScheduler spins up a loop. Calling
# init() once with an empty DSN sets a no-op client (no events sent, no quota
# burned) and unblocks the test stack. When SENTRY_DSN is set, we layer
# FastAPI + logging integrations on top so prod errors flow.
import os as _bootstrap_os
try:
    import sentry_sdk as _sentry
    _SENTRY_DSN = _bootstrap_os.getenv("SENTRY_DSN", "").strip()
    if _SENTRY_DSN:
        from sentry_sdk.integrations.fastapi import FastApiIntegration as _SentryFastAPI
        from sentry_sdk.integrations.logging import LoggingIntegration as _SentryLogging
        import logging as _logging
        _sentry.init(
            dsn=_SENTRY_DSN,
            environment=_bootstrap_os.getenv("SENTRY_ENV", "production"),
            release=_bootstrap_os.getenv("GIT_COMMIT", "unknown"),
            traces_sample_rate=0.05,
            send_default_pii=False,
            integrations=[
                _SentryFastAPI(),
                _SentryLogging(level=_logging.INFO, event_level=_logging.ERROR),
            ],
        )
    else:
        _sentry.init(dsn=None)
except Exception as _exc:
    print(f"[sentry] init skipped: {_exc}")

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db
from backend.db.migrate import run_migrations
from backend.db.seed import seed
from backend.api.routes import matches, predictions, betting, history, news, match3, groups
from backend.api.routes import teams, tournament, bracket_live, scenarios, push, sse_test, scoreboard, live, live_enriched, extras, wcdata, harvester_admin, model_picks, model_extras, players, match_recap, search
from backend.data.fetchers.results import refresh_form_cache
from backend.data.fetchers.odds import refresh_odds_cache
from backend.data.fetchers.scores import refresh_scores
from backend.data.fetchers.suspensions import refresh_match_events
from backend.data.refresh import start_scheduler, stop_scheduler
from backend.models.dc_ratings import ensure_fitted as ensure_dc_fitted, warn_missing as warn_dc_missing


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    run_migrations()
    seed()
    # Load external forecaster snapshots (Opta etc.) into the comparison tables.
    from backend.data.competitor_loader import load_opta_tournament
    from backend.db.session import SessionLocal as _SL_opta
    _db_opta = _SL_opta()
    try:
        try:
            r = load_opta_tournament(_db_opta)
            print(f"[startup] Opta tournament predictions loaded: {r['teams_loaded']} teams from {r['source_url']}")
        except Exception as _e:
            print(f"[startup] Opta loader skipped: {_e}")
    finally:
        _db_opta.close()
    from backend.data import feed_health
    await refresh_form_cache(); feed_health.record("form_refresh")
    await refresh_odds_cache(); feed_health.record("odds_refresh")
    await refresh_scores(); feed_health.record("score_refresh")
    await refresh_match_events(); feed_health.record("match_events")
    await ensure_dc_fitted(); feed_health.record("dc_refit")
    from backend.db.session import SessionLocal as _SL
    from backend.data.fetchers.tournament_form import rebuild as _rebuild_tf
    from backend.db.models import Team as _Team
    _db = _SL()
    try:
        _rebuild_tf(_db)
        # Surface any WC team silently missing from the DC fit (spelling drift, thin data)
        warn_dc_missing({t.code for t in _db.query(_Team).all()})
    finally:
        _db.close()
    # One-shot api-football probe so quota_budget._quota_remaining is populated
    # before any consumer's safe-by-default gate fires. Without this, every UTC
    # midnight (or container restart) leaves the harvester deadlocked: it won't
    # run until quota is observed, but only the harvester itself reports quota
    # back — so the counter stays None forever and the entire 7,500 daily
    # quota goes unused. Costs exactly 1 api-football call per backend start.
    try:
        import os as _os_probe
        import httpx as _httpx
        from backend.data import quota_budget as _qb_probe
        _key = _os_probe.getenv("API_FOOTBALL_KEY", "")
        if _key:
            r = _httpx.get(
                "https://v3.football.api-sports.io/timezone",
                headers={"x-apisports-key": _key},
                timeout=10.0,
            )
            daily = r.headers.get("x-ratelimit-requests-remaining")
            per_min = r.headers.get("x-ratelimit-remaining")
            _qb_probe.update_quota(
                int(daily) if daily and daily.isdigit() else None,
                int(per_min) if per_min and per_min.isdigit() else None,
            )
            print(f"[startup] api-football quota probe: daily={daily} per_minute={per_min}")
    except Exception as _exc:
        print(f"[startup] api-football quota probe failed: {_exc}")

    start_scheduler()
    # Warm the 20k-sim tournament projection in the background so the first homepage visitor
    # after a deploy never waits ~13s for a cold recompute (it persists across restarts too).
    import asyncio
    from backend.data.tournament_cache import refresh_tournament as _warm_tournament
    asyncio.create_task(_warm_tournament())

    # Seed the harvest queue (WC player stats + EPL/Bundesliga fixtures).
    # Dedup-safe — re-running on every startup only adds genuinely new jobs.
    # Gated by WC26_HARVEST so local dev never pollutes the queue or burns the
    # live API key. Default enabled; set WC26_HARVEST=0 in local .env to disable.
    try:
        from backend.data.quota_budget import harvester_enabled
        if not harvester_enabled():
            print("[startup] Harvest queue seed skipped (WC26_HARVEST=0)")
        else:
            from backend.data.harvester_seed import seed_full_stack
            seed_summary = seed_full_stack()
            print(f"[startup] Harvest queue seeded: {seed_summary['total_added']} new jobs (dedup skipped existing)")
    except Exception as _hs_err:
        print(f"[startup] Harvest queue seed skipped: {_hs_err}")

    yield
    stop_scheduler()


app = FastAPI(title="WC2026 Predictor API", lifespan=lifespan)

# Lock CORS to the known front-ends. The API is stateful (it writes the prediction
# ledger), so a wildcard origin needlessly invites cross-site abuse. Extra origins can
# be added via ALLOWED_ORIGINS (comma-separated) without a code change.
import os as _os

_DEFAULT_ORIGINS = [
    "https://wc26.tinjak.com",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_extra = [o.strip() for o in _os.getenv("ALLOWED_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_DEFAULT_ORIGINS + _extra,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

app.include_router(matches.router, prefix="/matches")
app.include_router(predictions.router, prefix="/matches")
app.include_router(betting.router, prefix="/betting")
app.include_router(history.router, prefix="/history")
app.include_router(news.router, prefix="/news")
app.include_router(match3.router, prefix="/match3")
app.include_router(groups.router, prefix="/groups")
app.include_router(teams.router, prefix="/teams")
app.include_router(tournament.router, prefix="/tournament")
app.include_router(bracket_live.router, prefix="/tournament")
app.include_router(scenarios.router, prefix="/groups")
app.include_router(push.router, prefix="/push")
app.include_router(sse_test.router, prefix="/sse")
app.include_router(scoreboard.router, prefix="/history")
app.include_router(harvester_admin.router, prefix="/harvester")
app.include_router(model_picks.router, prefix="/picks")
app.include_router(model_extras.router, prefix="/model")
app.include_router(players.router, prefix="/players-api")
app.include_router(match_recap.router, prefix="/matches")
app.include_router(live.router, prefix="/live")
app.include_router(extras.router, prefix="/extras")
app.include_router(live_enriched.router, prefix="/live")
app.include_router(wcdata.router, prefix="/wcdata")
app.include_router(search.router, prefix="/search")


@app.get("/health")
def health():
    """Liveness plus per-feed staleness so a silently-stopped data source is visible.

    `degraded` lists any feed older than a grace multiple of its refresh interval, and
    `odds_quota_remaining` surfaces how much of the odds budget is left before the value
    board and CLV capture go stale. `quota_budget` shows the api-football budget state
    (phase, remaining, harvester pacing).
    """
    from backend.data import feed_health
    from backend.data.fetchers import odds as _odds
    from backend.data import quota_budget as _qb

    fh = feed_health.snapshot()
    return {
        "status": "ok" if fh["all_fresh"] else "degraded",
        "commit": _os.getenv("GIT_COMMIT", "unknown"),
        "odds_quota_remaining": getattr(_odds, "_quota_remaining", None),
        "quota_budget": _qb.budget_summary(),
        **fh,
    }
