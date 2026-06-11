from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db
from backend.db.seed import seed
from backend.api.routes import matches, predictions, betting, history, news, match3, groups
from backend.data.fetchers.results import refresh_form_cache
from backend.data.fetchers.odds import refresh_odds_cache
from backend.data.fetchers.scores import refresh_scores
from backend.data.refresh import start_scheduler, stop_scheduler
from backend.models.dc_ratings import ensure_fitted as ensure_dc_fitted


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed()
    await refresh_form_cache()
    await refresh_odds_cache()
    await refresh_scores()
    await ensure_dc_fitted()
    # Seed in-tournament form from any already-completed matches in the DB
    from backend.db.session import SessionLocal as _SL
    from backend.data.fetchers.tournament_form import rebuild as _rebuild_tf
    _db = _SL()
    try:
        _rebuild_tf(_db)
    finally:
        _db.close()
    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="WC2026 Predictor API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


@app.get("/health")
def health():
    return {"status": "ok"}
