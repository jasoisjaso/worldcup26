"""WC2026 in-tournament results fed back into the form calculator.

Each completed WC2026 result is stored with today's date so form_modifier()
weights it at exp(-xi*0) = 1.0 — maximum influence. Called from refresh_scores()
after each score write and seeded at startup from existing completed matches.
"""
from datetime import datetime
from sqlalchemy.orm import Session

_cache: dict[str, list[tuple[str, str]]] = {}


def rebuild(db: Session) -> None:
    """Rebuild per-team tournament result cache from the DB."""
    from backend.db.models import Match

    today = datetime.utcnow().date().isoformat()
    completed = db.query(Match).filter(Match.status == "complete").all()
    new: dict[str, list[tuple[str, str]]] = {}
    for m in completed:
        if m.home_score is None or m.away_score is None:
            continue
        hs, as_ = m.home_score, m.away_score
        home_r = "W" if hs > as_ else ("D" if hs == as_ else "L")
        away_r = "W" if as_ > hs else ("D" if hs == as_ else "L")
        new.setdefault(m.home_code, []).append((today, home_r))
        new.setdefault(m.away_code, []).append((today, away_r))
    global _cache
    _cache = new


def get(team_code: str) -> list[tuple[str, str]]:
    """Tournament results for a team, all dated today for max time-weight."""
    return list(_cache.get(team_code, []))
