"""Enriched live hub — events, api-football predictions, fair odds, key players."""
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.db.models import (
    Match, Team, OddsCache, LiveMatchState, LiveWpHistory,
    MatchEvent, ApiFootballPrediction, PlayerProfile, PlayerTournamentStats,
    MatchStatistics,
)
from backend.data.fetchers.live_enrich import get_live_events, get_prediction
from backend.data.fetchers.injuries import TEAM_IDS
from backend.betting.market import devig_shin
from backend.util.datetime import iso_utc

router = APIRouter()


def _key_players(db: Session, team_code: str | None) -> list[dict]:
    """Top 3 players for a team by goal contribution. Uses harvested
    PlayerProfile (for photo + name) joined with PlayerTournamentStats
    (for goals/assists). Returns [] for teams not yet harvested."""
    if not team_code:
        return []
    api_team_id = TEAM_IDS.get(team_code.lower())
    if not api_team_id:
        return []
    rows = (
        db.query(PlayerTournamentStats, PlayerProfile)
        .join(PlayerProfile, PlayerProfile.player_id == PlayerTournamentStats.player_id)
        .filter(PlayerTournamentStats.team_id == api_team_id)
        .filter((PlayerTournamentStats.goals > 0) | (PlayerTournamentStats.assists > 0))
        .order_by(
            (PlayerTournamentStats.goals + PlayerTournamentStats.assists).desc(),
            PlayerTournamentStats.goals.desc(),
        )
        .limit(3)
        .all()
    )
    return [
        {
            "id": p.player_id,
            "name": p.name,
            "photo_url": p.photo_url,
            "position": p.position,
            "goals": s.goals or 0,
            "assists": s.assists or 0,
        }
        for s, p in rows
    ]

LIVE_STALE_MINUTES = 5  # tightened so finished-but-not-yet-FT rows drop fast


def _fair_odds(db: Session, match_id: str) -> dict:
    """1X2 fair odds and implied probabilities from our devigged market consensus."""
    buckets = {"home_win": [], "draw": [], "away_win": []}
    for r in db.query(OddsCache).filter(OddsCache.match_id == match_id).all():
        if r.market in buckets:
            buckets[r.market].append(r.odds)

    fair = {"home": None, "draw": None, "away": None}
    probs = {"home": None, "draw": None, "away": None}

    if all(len(buckets[k]) >= 2 for k in buckets):
        avg_odds = [sum(buckets[m]) / len(buckets[m]) for m in ["home_win", "draw", "away_win"]]
        try:
            fp = devig_shin(avg_odds)
            if fp:
                for i, k in enumerate(["home", "draw", "away"]):
                    if fp[i] and fp[i] > 0:
                        fair[k] = round(fp[i], 2)
                        probs[k] = round(1.0 / fp[i], 3)
        except Exception:
            pass
    return {"fair_odds": fair, "implied_probs": probs}


def _resolve_api_fixture_id(db: Session, match_id: str) -> int | None:
    """Read api-football fixture id from LiveMatchState — already populated by the poller.
    Saves ~240 redundant /fixtures?live=all calls per hour during busy days."""
    lms = db.query(LiveMatchState).filter(LiveMatchState.match_id == match_id).first()
    return lms.fixture_id_external if lms else None


def _resolve_team_api_id(db: Session, code: str | None) -> int | None:
    """Internal code → api-football team id, via the static TEAM_IDS table."""
    if not code:
        return None
    return TEAM_IDS.get(code.lower())


@router.get("/hub/enriched")
async def live_hub_enriched(db: Session = Depends(get_db)):
    """All currently live WC matches with events + predictions + fair odds.

    A row is "live" only if status is an in-play code AND it has been touched by
    the poller in the last LIVE_STALE_MINUTES minutes. The api-football live
    endpoint drops a match the moment it goes FT, so a stuck "2H"/"95" row
    without a recent update means the match ended — surface it as finished, not
    live, until the score_refresh job fills in the result.
    """
    cutoff = datetime.utcnow() - timedelta(minutes=LIVE_STALE_MINUTES)
    states = (
        db.query(LiveMatchState)
        .filter(LiveMatchState.status.in_(["1H", "HT", "2H", "ET", "BT", "P", "LIVE"]))
        .filter(LiveMatchState.updated_at >= cutoff)
        .all()
    )
    out = []
    for s in states:
        match = db.query(Match).filter(Match.id == s.match_id).first()
        if not match:
            continue
        home = db.query(Team).filter(Team.code == match.home_code).first()
        away = db.query(Team).filter(Team.code == match.away_code).first()

        last_tick = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.id.desc()).first()
        )
        ticks = (
            db.query(LiveWpHistory)
            .filter(LiveWpHistory.match_id == s.match_id)
            .order_by(LiveWpHistory.elapsed_min.asc(), LiveWpHistory.id.asc()).all()
        )

        api_fid = _resolve_api_fixture_id(db, match.id)

        # Events: pull from persistent archive (written by the live poller every 30s).
        # Live matches: archive is fresh. Finished matches: archive is the source of truth.
        archived_events = (
            db.query(MatchEvent)
            .filter(MatchEvent.match_id == match.id)
            .order_by(MatchEvent.elapsed.asc(), MatchEvent.id.asc())
            .all()
        )
        if archived_events:
            events = [{
                "elapsed": e.elapsed, "extra": e.extra,
                "type": e.type, "detail": e.detail,
                "player_name": e.player_name, "player_id": e.player_id,
                "assist_name": e.assist_name, "team_name": e.team_name,
                "team_id": e.team_id,
                # ShootoutTracker needs this: api-football stamps shootout kicks
                # elapsed=120 + comments="Penalty Shootout", so without comments
                # the FE can't tell a shootout kick from an ET penalty.
                "comments": e.comments,
            } for e in archived_events]
        else:
            events = await get_live_events(api_fid) if api_fid else []

        # Prediction: prefer the persisted snapshot (written once 24h pre-kickoff).
        # Only call the API if we somehow don't have one yet.
        snap = (
            db.query(ApiFootballPrediction)
            .filter(ApiFootballPrediction.match_id == match.id)
            .first()
        )
        if snap:
            api_pred = {
                "winner_name": snap.winner_name, "winner_comment": snap.winner_comment,
                "advice": snap.advice, "win_or_draw": snap.win_or_draw,
                "pct_home": snap.pct_home, "pct_draw": snap.pct_draw, "pct_away": snap.pct_away,
                "form_home": snap.comp_form_home, "form_away": snap.comp_form_away,
                "h2h_home": snap.comp_h2h_home, "h2h_away": snap.comp_h2h_away,
            }
        else:
            api_pred = await get_prediction(api_fid) if api_fid else None

        odds_data = _fair_odds(db, match.id)

        # Live statistics — per-team rows written by the live poller every 30s
        # into MatchStatistics. Covers corners, fouls, offsides, saves, passes
        # accuracy — the bet-worthy details LiveMatchState doesn't carry.
        stat_rows = (
            db.query(MatchStatistics)
            .filter(MatchStatistics.match_id == match.id)
            .all()
        )
        home_stats = next((s for s in stat_rows if s.team_id and home and s.team_id == _resolve_team_api_id(db, home.code)), None) if home else None
        away_stats = next((s for s in stat_rows if s.team_id and away and s.team_id == _resolve_team_api_id(db, away.code)), None) if away else None
        # Fallback: by index when team_id resolution fails
        if not home_stats and not away_stats and len(stat_rows) >= 2:
            home_stats, away_stats = stat_rows[0], stat_rows[1]

        def _stats_dict(s):
            if not s:
                return None
            return {
                "possession_pct": s.ball_possession,
                "shots_total": s.total_shots,
                "shots_on_target": s.shots_on_goal,
                "shots_off_target": s.shots_off_goal,
                "shots_blocked": s.blocked_shots,
                "shots_inside_box": s.shots_inside_box,
                "shots_outside_box": s.shots_outside_box,
                "corners": s.corner_kicks,
                "fouls": s.fouls,
                "offsides": s.offsides,
                "yellow_cards": s.yellow_cards,
                "red_cards": s.red_cards,
                "saves": s.goalkeeper_saves,
                "passes_total": s.total_passes,
                "passes_accurate": s.passes_accurate,
                "passes_pct": s.passes_pct,
                "xg": s.expected_goals,
            }

        # Tally yellow cards from MatchEvent as a fallback when MatchStatistics
        # rows haven't been written yet (early in a match).
        yc_home = sum(1 for e in archived_events if (e.type == "Card" and e.detail and "Yellow" in (e.detail or "") and e.team_name and home and e.team_name == home.name))
        yc_away = sum(1 for e in archived_events if (e.type == "Card" and e.detail and "Yellow" in (e.detail or "") and e.team_name and away and e.team_name == away.name))

        out.append({
            "match_id": s.match_id,
            "group": match.group,
            "matchday": match.matchday,
            "home_code": match.home_code,
            "away_code": match.away_code,
            "home_name": home.name if home else match.home_code.upper(),
            "away_name": away.name if away else match.away_code.upper(),
            "home_flag": home.flag_url if home else None,
            "away_flag": away.flag_url if away else None,
            "kickoff": iso_utc(match.kickoff),
            "key_players": {
                "home": _key_players(db, match.home_code),
                "away": _key_players(db, match.away_code),
            },
            "state": {
                "status": s.status, "elapsed_min": s.elapsed_min,
                "home_score": s.home_score, "away_score": s.away_score,
                "home_red_cards": s.home_red_cards, "away_red_cards": s.away_red_cards,
                "home_possession": s.home_possession, "away_possession": s.away_possession,
                "home_shots": s.home_shots, "away_shots": s.away_shots,
                "home_shots_on_target": s.home_shots_on_target, "away_shots_on_target": s.away_shots_on_target,
                "home_xg": s.home_xg, "away_xg": s.away_xg,
                # Shootout score (only populated when status in {"P","PEN"}).
                # Frontend uses presence as the trigger to render the
                # ball-by-ball ShootoutTracker component.
                "shootout_home_score": s.shootout_home_score,
                "shootout_away_score": s.shootout_away_score,
            },
            "wp": {
                "p_home": last_tick.p_home, "p_draw": last_tick.p_draw, "p_away": last_tick.p_away,
            } if last_tick else None,
            "sparkline": [
                {"e": t.elapsed_min, "h": round(t.p_home, 3), "a": round(t.p_away, 3)}
                for t in ticks[-30:]
            ],
            "events": events,
            "api_prediction": api_pred,
            "fair_odds": odds_data["fair_odds"],
            "implied_probs": odds_data["implied_probs"],
            "live_stats": {
                "home": _stats_dict(home_stats),
                "away": _stats_dict(away_stats),
                "yellow_card_count": {"home": yc_home, "away": yc_away},
            },
        })
    out.sort(key=lambda x: -(x["state"]["elapsed_min"] or 0))
    return {"live_count": len(out), "matches": out}
