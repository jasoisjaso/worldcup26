"""
Match-specific lambda modifiers for WC2026 group stage.

Independent effects applied after base DC/ELO lambdas:
  1. altitude_lambda_bonus     - both teams score more at high-altitude venues
  2. rest_days_multipliers     - relative rest gap since last WC game
  3. dead_rubber_multipliers   - squads rotating starters in settled MD3 games
  4. travel_multipliers        - long-haul travel between WC2026 venues with short rest

md1_rho() returns the (single, fitted) Dixon-Coles rho; see its docstring for why the
former MD1 override was removed.
"""
from __future__ import annotations
import math
from datetime import datetime
from sqlalchemy.orm import Session

# High-altitude venues (metres above sea level from venue_advantage.py)
# Research consensus: ~0.10-0.15 additional expected goals per team at 2240m
# Both teams score more — reduced air resistance, ball pace, keeper/defender fatigue
_VENUE_ALTITUDE_BONUS: dict[str, float] = {
    "mexico city": 0.12,   # 2240m — Estadio Azteca
    "guadalajara": 0.06,   # 1522m — Estadio Akron
    # Monterrey 538m: below threshold, no adjustment
}

# Rest days: each day of advantage over opponent = +2% lambda, capped at ±6%
_REST_PER_DAY = 0.02
_REST_CAP = 0.06

# WC2026: top 2 per group + best 8 third-place finishers advance to R32
# Confirmed qualified (6 pts): still full dead rubber
# Likely eliminated (0 pts + 2 others at 6 pts): softer reduction because the
# team still mathematically competes for best-8-third-place position
_DEAD_RUBBER_FACTOR = 0.87
_LIKELY_ELIMINATED_FACTOR = 0.92

DEFAULT_RHO = -0.13


def md1_rho(matchday: int | None) -> float:
    """Return the DC rho to use for the score matrix.

    Historically this relaxed rho to -0.05 on MD1 "to inflate draws", but that was
    backwards: the dominant draw term is the (1,1) cell, tau(1,1)=1-rho, so a
    *less* negative rho *shrinks* the draw boost (1.13x -> 1.05x) and yields ~2pp
    FEWER draws — the opposite of the stated goal. The walk-forward backtest also
    shows no 1X2 RPS benefit from the override, so it is removed and rho is kept at
    the fitted -0.13 for all matchdays (consistent with how alpha/beta were fitted).
    """
    return DEFAULT_RHO


def _city_key(venue: str) -> str:
    parts = venue.lower().split(",")
    return parts[-1].strip() if parts else ""


def altitude_lambda_bonus(venue: str) -> float:
    """
    Additive expected-goals bonus applied to BOTH teams at high-altitude venues.
    Called from group_predictor before form modifier.
    """
    return _VENUE_ALTITUDE_BONUS.get(_city_key(venue), 0.0)


def rest_days_multipliers(
    home_code: str,
    away_code: str,
    match_kickoff: datetime,
    db: Session,
) -> tuple[float, float]:
    """
    Return (home_mult, away_mult) based on relative rest since last WC game.
    A team with 3 more days rest than their opponent gets a +6% lambda boost.
    First match of tournament (no previous game) → 1.0 for both.
    """
    from backend.db.models import Match as DBMatch

    completed = (
        db.query(DBMatch)
        .filter(DBMatch.status == "complete", DBMatch.kickoff.isnot(None))
        .all()
    )

    match_date = match_kickoff.date() if isinstance(match_kickoff, datetime) else match_kickoff

    def last_wc_date(code: str):
        dates = [
            m.kickoff.date()
            for m in completed
            if (m.home_code == code or m.away_code == code) and m.kickoff
        ]
        return max(dates) if dates else None

    home_last = last_wc_date(home_code)
    away_last = last_wc_date(away_code)

    if home_last is None and away_last is None:
        return 1.0, 1.0

    home_days = (match_date - home_last).days if home_last else 0
    away_days = (match_date - away_last).days if away_last else 0
    diff = home_days - away_days

    home_mult = 1.0 + max(-_REST_CAP, min(_REST_CAP, diff * _REST_PER_DAY))
    away_mult = 1.0 + max(-_REST_CAP, min(_REST_CAP, -diff * _REST_PER_DAY))
    return home_mult, away_mult


def dead_rubber_multipliers(
    home_code: str,
    away_code: str,
    matchday: int,
    group: str,
    db: Session,
) -> tuple[float, float]:
    """
    Return (home_factor, away_factor). Applies _DEAD_RUBBER_FACTOR (0.87) if the
    team already has qualification or elimination confirmed before MD3 kicks off.

    Qualified: 6 points (won both MD1+MD2 games) — guaranteed top-2 in a group of 4.
    Eliminated: 0 points + 2 other group teams already on 6 pts (both spots taken).
    """
    if matchday != 3:
        return 1.0, 1.0

    from backend.db.models import Match as DBMatch

    completed = [
        m for m in db.query(DBMatch).filter(
            DBMatch.status == "complete",
            DBMatch.group == group,
            DBMatch.matchday < 3,
        ).all()
        if m.home_score is not None and m.away_score is not None
    ]

    points: dict[str, int] = {}
    group_teams: set[str] = set()
    for m in completed:
        group_teams.add(m.home_code)
        group_teams.add(m.away_code)
        hs, as_ = m.home_score, m.away_score
        points[m.home_code] = points.get(m.home_code, 0) + (3 if hs > as_ else (1 if hs == as_ else 0))
        points[m.away_code] = points.get(m.away_code, 0) + (3 if as_ > hs else (1 if hs == as_ else 0))

    def _dead_rubber_factor(code: str) -> float:
        my_pts = points.get(code, 0)
        if my_pts >= 6:
            return _DEAD_RUBBER_FACTOR  # guaranteed top-2
        others = [points.get(t, 0) for t in group_teams if t != code]
        if my_pts == 0 and sum(1 for p in others if p >= 6) >= 2:
            return _LIKELY_ELIMINATED_FACTOR  # still alive for best-8-third
        return 1.0

    return _dead_rubber_factor(home_code), _dead_rubber_factor(away_code)


# WC2026 venue coordinates — must match _city_key() output
_VENUE_COORDS: dict[str, tuple[float, float]] = {
    "new york":      (40.8135, -74.0745),
    "new jersey":    (40.8135, -74.0745),
    "los angeles":   (34.0141, -118.2879),
    "dallas":        (32.7479,  -97.0929),
    "san francisco": (37.4033, -121.9696),
    "seattle":       (47.5952, -122.3316),
    "miami":         (25.9579,  -80.2389),
    "boston":        (42.0908,  -71.2641),
    "kansas city":   (39.0489,  -94.4839),
    "atlanta":       (33.7553,  -84.4006),
    "houston":       (29.6847,  -95.4107),
    "philadelphia":  (39.9008,  -75.1675),
    "vancouver":     (49.2767, -123.1125),
    "toronto":       (43.6332,  -79.4170),
    "guadalajara":   (20.6846, -103.3169),
    "mexico city":   (19.3030,  -99.1500),
    "monterrey":     (25.6694, -100.3097),
}


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return 6371.0 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def travel_multipliers(
    home_code: str,
    away_code: str,
    current_venue: str,
    match_kickoff: datetime,
    db: Session,
) -> tuple[float, float]:
    """
    Penalty for teams that travelled >1000km since their last WC match with ≤5 days rest.
    WC2026 spans NYC→Vancouver (4700km) — unique tournament travel burden.
    Short-hop travel (<1000km) has no effect; long-haul with short rest does.
    """
    from backend.db.models import Match as DBMatch

    curr_city = _city_key(current_venue)
    if curr_city not in _VENUE_COORDS:
        return 1.0, 1.0

    curr_lat, curr_lon = _VENUE_COORDS[curr_city]
    match_date = match_kickoff.date() if isinstance(match_kickoff, datetime) else match_kickoff

    completed = (
        db.query(DBMatch)
        .filter(DBMatch.status == "complete", DBMatch.kickoff.isnot(None))
        .all()
    )

    def _penalty(code: str) -> float:
        last = None
        for m in completed:
            if (m.home_code == code or m.away_code == code) and m.kickoff and m.venue:
                if last is None or m.kickoff > last[0]:
                    last = (m.kickoff, m.venue)
        if not last:
            return 1.0
        days_since = (match_date - last[0].date()).days
        if days_since > 5:
            return 1.0  # enough recovery time
        last_city = _city_key(last[1])
        if last_city not in _VENUE_COORDS:
            return 1.0
        prev_lat, prev_lon = _VENUE_COORDS[last_city]
        dist_km = _haversine_km(prev_lat, prev_lon, curr_lat, curr_lon)
        if dist_km > 3500:
            return 0.96
        if dist_km > 2000:
            return 0.97
        if dist_km > 1000:
            return 0.99
        return 1.0

    return _penalty(home_code), _penalty(away_code)
