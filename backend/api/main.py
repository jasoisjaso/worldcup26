from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db
from backend.db.migrate import run_migrations
from backend.db.seed import seed
from backend.api.routes import matches, predictions, betting, history, news, match3, groups
from backend.api.routes import teams, tournament, bracket_live, scenarios, push, sse_test, scoreboard, live, live_enriched, extras, wcdata, harvester_admin, model_picks, model_extras
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
    start_scheduler()
    # Warm the 20k-sim tournament projection in the background so the first homepage visitor
    # after a deploy never waits ~13s for a cold recompute (it persists across restarts too).
    import asyncio
    from backend.data.tournament_cache import refresh_tournament as _warm_tournament
    asyncio.create_task(_warm_tournament())
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
app.include_router(live.router, prefix="/live")
app.include_router(extras.router, prefix="/extras")
app.include_router(live_enriched.router, prefix="/live")
app.include_router(wcdata.router, prefix="/wcdata")


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
