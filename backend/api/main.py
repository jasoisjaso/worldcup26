from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.db.session import init_db
from backend.db.seed import seed
from backend.api.routes import matches, predictions, betting, history, news, match3
from backend.data.fetchers.results import refresh_form_cache
from backend.data.refresh import start_scheduler, stop_scheduler


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    seed()
    await refresh_form_cache()
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


@app.get("/health")
def health():
    return {"status": "ok"}
