from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import Match, Team

router = APIRouter()


def _team_dict(team: Team) -> dict:
    return {
        "code": team.code,
        "name": team.name,
        "fifa_code": team.fifa_code,
        "elo": team.elo,
        "fifa_ranking": team.fifa_ranking,
        "flag_url": team.flag_url,
        "primary_color": team.primary_color,
    }


def _match_dict(match: Match, home: Team, away: Team) -> dict:
    return {
        "id": match.id,
        "group": match.group,
        "matchday": match.matchday,
        "kickoff": iso_utc(match.kickoff),
        "venue": match.venue,
        "status": match.status,
        "home": _team_dict(home),
        "away": _team_dict(away),
        "actual_score": (
            {"home": match.home_score, "away": match.away_score}
            if match.home_score is not None
            else None
        ),
        # Shootout tiebreaker for knockout matches decided on penalties. NULL
        # for the 99% of fixtures decided in regulation or extra time — the FE
        # treats absence as "no shootout", presence as "render the (X-Y pens)
        # suffix and the shootout breakdown". See LIVE_KNOCKOUTS_AND_SHOOTOUTS.md.
        "shootout_score": (
            {"home": match.shootout_home_score, "away": match.shootout_away_score}
            if match.shootout_home_score is not None or match.shootout_away_score is not None
            else None
        ),
        # Half-time scoreline so the FE can render "HT: 0-2" alongside the FT
        # scoreline (2026-06-21). Null when we don't have it yet — the
        # backfill scheduler populates it from harvested /fixtures blobs.
        "ht_score": (
            {"home": match.home_ht_score, "away": match.away_ht_score}
            if match.home_ht_score is not None and match.away_ht_score is not None
            else None
        ),
        # Interruption lifecycle (FRA-IRQ 2026-06-22 fix). NULL for the
        # 99% case. When set, the FE renders a coloured badge in place of
        # the FT score so users never see a phantom "FT 1-0" on a paused
        # match. partial_score is the snapshot at the moment play stopped.
        "interruption_status": match.interruption_status,
        "interruption_reason": match.interruption_reason,
        "partial_score": (
            {"home": match.partial_home_score, "away": match.partial_away_score}
            if match.partial_home_score is not None and match.partial_away_score is not None
            else None
        ),
    }


@router.get("")
def get_matches(group: str | None = None, matchday: int | None = None, db: Session = Depends(get_db)):
    query = db.query(Match)
    if group:
        query = query.filter(Match.group == group.upper())
    if matchday:
        query = query.filter(Match.matchday == matchday)
    matches = query.order_by(Match.kickoff).all()

    result = []
    for m in matches:
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if home and away:
            result.append(_match_dict(m, home, away))
    return result


@router.get("/{match_id}")
def get_match(match_id: str, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)
    return _match_dict(m, home, away)


from pydantic import BaseModel  # noqa: E402
from backend.util.datetime import iso_utc


class ScoreUpdate(BaseModel):
    home_score: int
    away_score: int
    status: str = "complete"


@router.patch("/{match_id}/score")
def update_score(match_id: str, body: ScoreUpdate, db: Session = Depends(get_db)):
    m = db.get(Match, match_id)
    if not m:
        raise HTTPException(status_code=404, detail="Match not found")
    m.home_score = body.home_score
    m.away_score = body.away_score
    m.status = body.status
    db.commit()
    home = db.get(Team, m.home_code)
    away = db.get(Team, m.away_code)
    return _match_dict(m, home, away)


@router.get("/{match_id}/pre-match-context")
async def get_pre_match_context(match_id: str, db: Session = Depends(get_db)):
    """Everything a user needs to decide a bet without leaving the match page:
    stakes, last-5 form rows for each team, season averages (goals/corners/cards/
    BTTS%/CS%/xG/possession), H2H summary, absences, and the model's swing in
    win probability from the known absences.

    All pure DB reads except `model_swing_from_absences`, which runs the
    prediction pipeline twice (once with real modifiers, once with neutral)
    and reports the home_win delta in percentage points.
    """
    from backend.data.match_context import build_pre_match_context
    from backend.models.group_predictor import predict_group_match
    from backend.models.prediction_inputs import assemble

    ctx = build_pre_match_context(match_id, db)
    if ctx is None:
        raise HTTPException(status_code=404, detail="Match not found")

    # Layered async piece: model swing from absences.
    # We run predict twice — once with the real modifiers, once with neutral
    # lineup+injury+suspension multipliers — and report the delta in home_win.
    try:
        m = db.get(Match, match_id)
        if m is None:
            ctx["model_swing_from_absences"] = None
            return ctx
        home = db.get(Team, m.home_code)
        away = db.get(Team, m.away_code)
        if not home or not away:
            ctx["model_swing_from_absences"] = None
            return ctx
        full_ctx = await assemble(m, home, away, db)
        # Predict WITH all modifiers (the live truth) ...
        pred_real = predict_group_match(
            full_ctx["home_input"], full_ctx["away_input"],
            venue_context=full_ctx["venue_context"], matchday=m.matchday,
            **full_ctx["modifiers"],
        )
        # ... then strip the absence-related modifiers and predict again.
        neutral_mods = dict(full_ctx["modifiers"])
        for k in ("lineup_multipliers", "injury_multipliers", "suspension_multipliers"):
            if k in neutral_mods:
                neutral_mods[k] = (1.0, 1.0)
        pred_neutral = predict_group_match(
            full_ctx["home_input"], full_ctx["away_input"],
            venue_context=full_ctx["venue_context"], matchday=m.matchday,
            **neutral_mods,
        )
        ctx["model_swing_from_absences"] = {
            "home_pp": round((pred_real.home_win - pred_neutral.home_win) * 100, 1),
            "away_pp": round((pred_real.away_win - pred_neutral.away_win) * 100, 1),
        }
    except Exception as exc:
        # The swing calc is a nicety, not a contract — never block the brief
        # because the prediction pipeline hiccuped.
        ctx["model_swing_from_absences"] = {"error": str(exc)[:120]}

    return ctx
