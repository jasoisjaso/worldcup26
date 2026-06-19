"""Public forecaster scoreboard — us vs Bet365 vs Opta on the same data."""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.db.models import CompetitorTournamentPrediction
from backend.data.tournament_cache import get_tournament
from backend.eval.comparison import scoreboard

router = APIRouter()


@router.get("/scoreboard")
async def get_scoreboard(db: Session = Depends(get_db)):
    """Per-match scoring against settled matches: us vs Bet365 closing line."""
    return scoreboard(db)


@router.get("/scoreboard/tournament")
async def get_tournament_scoreboard(db: Session = Depends(get_db)):
    """Tournament-level side-by-side: per-team title / advance probabilities,
    us vs every external forecaster (currently Opta).

    No scoring is applied yet — these resolve once the tournament progresses (a team
    is either eliminated or advances). The page just shows where we agree and disagree
    with Opta. Disagreements become news.
    """
    ours = await get_tournament(db)
    our_by_code = {t["code"]: t for t in ours["teams"]}

    rows = (
        db.query(CompetitorTournamentPrediction)
        .filter(CompetitorTournamentPrediction.forecaster == "opta")
        .all()
    )

    out = []
    for r in rows:
        ours_t = our_by_code.get(r.team_code)
        if not ours_t:
            continue
        out.append({
            "code": r.team_code,
            "name": ours_t["name"],
            "flag_url": ours_t.get("flag_url"),
            "us": {
                "p_title":    ours_t.get("p_title"),
                "p_advance":  ours_t.get("p_advance"),
                "p_first":    ours_t.get("p_first"),
                "p_r16":      ours_t.get("p_r16"),
                "p_quarter":  ours_t.get("p_quarter"),
            },
            "opta": {
                "p_title":    r.p_title,
                "p_advance":  r.p_advance,
                "p_first":    r.p_first,
                "p_r16":      r.p_r16,
                "p_quarter":  r.p_quarter,
            },
            "title_delta": (ours_t.get("p_title") or 0) - (r.p_title or 0),
            "advance_delta": (ours_t.get("p_advance") or 0) - (r.p_advance or 0),
        })
    # Sort by title disagreement size — most contrarian picks float to the top
    out.sort(key=lambda x: abs(x["title_delta"] or 0), reverse=True)
    return {
        "n_teams": len(out),
        "opta_source": rows[0].source_url if rows else None,
        "opta_captured": rows[0].captured_at if rows else None,
        "teams": out,
    }
