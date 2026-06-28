"""Cached tournament Monte Carlo.

Running the full-context model over all 72 fixtures (``assemble`` hits several cached
fetchers per match) plus a 20k-run simulation takes a few seconds, so the result is cached
in-process and only recomputed when results change or the TTL lapses. The scheduler warms
it so the first visitor never waits. A fixed RNG seed keeps the published numbers stable
between refreshes (Monte-Carlo noise at 20k runs is sub-0.5pp anyway)."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import time

from sqlalchemy.orm import Session

from backend.db.models import Match, Team
from backend.db.session import SessionLocal
from backend.models.group_predictor import predict_group_match
from backend.models.prediction_inputs import assemble
from backend.models.tournament_sim import SimMatch, simulate_tournament
from backend.version import MODEL_VERSION

logger = logging.getLogger(__name__)

_N_SIMS = 20000
_SEED = 20260611  # fixed -> stable published numbers
_TTL = 1800.0  # 30 min

_CACHE: dict = {"data": None, "ts": 0.0, "sig": None}
_LOCK = asyncio.Lock()
# Persisted to the data volume so a deploy/restart reloads the projection instead of forcing
# the next visitor to wait ~13s for a cold 20k-sim recompute (the cause of "site won't load"
# right after a deploy). Reloaded if the result signature still matches.
_PERSIST_PATH = os.path.join(
    os.path.dirname(os.getenv("DATABASE_URL", "sqlite:///./data/x").replace("sqlite:///", "")),
    "tournament_cache.json",
)


def _persist() -> None:
    if _CACHE["data"] is None:
        return
    try:
        with open(_PERSIST_PATH, "w") as f:
            json.dump({"data": _CACHE["data"], "ts": _CACHE["ts"], "sig": list(_CACHE["sig"])}, f)
    except Exception as e:  # noqa: BLE001
        logger.warning("tournament cache persist failed: %s", e)


def _load() -> None:
    if _CACHE["data"] is not None:
        return
    try:
        with open(_PERSIST_PATH) as f:
            d = json.load(f)
    except FileNotFoundError:
        return
    except Exception as e:  # noqa: BLE001
        logger.warning("tournament cache load failed: %s", e)
        return
    if d.get("data"):
        _CACHE.update(data=d["data"], ts=d.get("ts", 0.0), sig=tuple(d.get("sig") or []))
        logger.info("Loaded persisted tournament projection (sig %s)", _CACHE["sig"])


def _signature(db: Session) -> tuple:
    """Cheap fingerprint that changes whenever results land (the dominant driver of the
    simulation), so a finished match invalidates the cache immediately."""
    rows = db.query(Match.status, Match.home_score, Match.away_score).all()
    completed = sum(1 for s, _, _ in rows if s == "complete")
    goals = sum((h or 0) + (a or 0) for _, h, a in rows)
    return (completed, goals, MODEL_VERSION)


async def _compute(db: Session) -> dict:
    # Group-stage matches only. The tournament simulator runs the group stage
    # forward 20K times to derive third-place qualifiers + standings, then
    # applies the bracket structure to those standings. Knockout matches in the
    # DB are downstream of the simulation, not inputs to it — feeding them in
    # would route 32 KO teams into a single `groups["?"]` bucket, which breaks
    # the third-place resolver (KeyError on the synthetic key "????????").
    matches_db = db.query(Match).filter(Match.matchday <= 3).all()
    teams = {t.code: t for t in db.query(Team).all()}

    sim_matches: list[SimMatch] = []
    lambdas: dict[str, tuple[float, float]] = {}
    for m in matches_db:
        sm = SimMatch(
            id=m.id, group=m.group or "?", home=m.home_code, away=m.away_code,
            status=m.status or "upcoming", home_score=m.home_score, away_score=m.away_score,
        )
        sim_matches.append(sm)
        if sm.status == "complete":
            continue
        home, away = teams.get(m.home_code), teams.get(m.away_code)
        if not home or not away:
            continue
        ctx = await assemble(m, home, away, db)
        pred = predict_group_match(
            ctx["home_input"], ctx["away_input"],
            venue_context=ctx["venue_context"], matchday=m.matchday, **ctx["modifiers"],
        )
        lambdas[m.id] = (pred.lambda_home, pred.lambda_away)

    names = {c: t.name for c, t in teams.items()}
    flags = {c: (t.flag_url or "") for c, t in teams.items()}
    colors = {c: (t.primary_color or "") for c, t in teams.items()}
    elos = {c: (t.elo or 1500.0) for c, t in teams.items()}

    # The heavy numpy + ranking loop runs off the event loop.
    result = await asyncio.to_thread(
        simulate_tournament, sim_matches, lambdas, elos, None, _N_SIMS, _SEED, names,
    )
    for row in result["teams"]:
        row["flag_url"] = flags.get(row["code"], "")
        row["primary_color"] = colors.get(row["code"], "")
    result["model_version"] = MODEL_VERSION
    result["completed_matches"] = sum(1 for m in sim_matches if m.status == "complete")
    return result


async def get_tournament(db: Session) -> dict:
    sig = _signature(db)
    now = time.time()
    # Cold process (just deployed): reload the persisted projection so this request does not
    # pay for a full recompute. Served only while its signature still matches (no new result).
    if _CACHE["data"] is None:
        _load()
    if _CACHE["data"] is not None and _CACHE["sig"] == sig and (now - _CACHE["ts"]) < _TTL:
        return _CACHE["data"]
    async with _LOCK:
        if _CACHE["data"] is not None and _CACHE["sig"] == sig and (time.time() - _CACHE["ts"]) < _TTL:
            return _CACHE["data"]
        data = await _compute(db)
        _CACHE.update(data=data, ts=time.time(), sig=sig)
        _persist()
        return data


async def refresh_tournament() -> None:
    """Scheduler entry point — recompute and warm the cache."""
    db = SessionLocal()
    try:
        data = await _compute(db)
        _CACHE.update(data=data, ts=time.time(), sig=_signature(db))
        _persist()
        print(f"[tournament] simulation refreshed ({data.get('completed_matches', 0)} results in)")
    except Exception as e:  # never let a scheduler job crash the loop
        print(f"[tournament] refresh failed: {e}")
    finally:
        db.close()
