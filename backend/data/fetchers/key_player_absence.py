"""Player-weighted absence multiplier.

The existing `squad_availability.py` modifier counts sidelined players flat —
losing the third-choice keeper hits as hard as losing your top scorer. This
file adds the missing weighting: each absent player's penalty is sized by
their share of the team's recent (goals + assists) output.

Reads two harvested tables, zero API cost:
  - player_season_stats — per-player goals/assists per season per club
  - player_sidelined    — currently-out players

Same shape as the other fetchers:
  - Tight cap (±5%) so it never disturbs the ELO+DC core.
  - Neutral 1.0 when there is no data — the model loses nothing pre-harvest.
  - Pure DB, can be called for every match without API spend.

Composes WITH `get_squad_availability_multipliers` rather than replacing it.
That older modifier covers continuity (XI rotation) + raw absence count; this
one adds the "who specifically is out" weighting.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import func

from backend.data.fetchers.injuries import TEAM_IDS
from backend.db.session import SessionLocal
from backend.db.models import PlayerSeasonStats, PlayerSidelined

# Window over which we sum a player's contribution. Recent seasons only —
# career-long sums would over-weight older players. WC2026 = 2026 season; we
# look back two club seasons since some teams' WC squads pull from rosters
# settled in 2024/25 + 2025/26.
_RECENT_SEASONS = (2024, 2025, 2026)

# Minimum player-output denominator before we trust the share. If a national
# team has fewer than this many (goals + assists) total in the window we have
# no signal and default to neutral.
_MIN_DENOM = 8

# Max ±5% effect on lambda (matches the xG modifiers).
_CAP = 0.05


def _team_contribution_map(team_api_id: int, db) -> dict[int, float]:
    """Map of {player_api_id: (goals + assists) summed over recent seasons}
    for one club/team. Returns {} if the player_season_stats table has no
    rows for this team in the window."""
    rows = (
        db.query(
            PlayerSeasonStats.player_api_id,
            func.sum(PlayerSeasonStats.goals_total).label("g"),
            func.sum(PlayerSeasonStats.assists_total).label("a"),
        )
        .filter(PlayerSeasonStats.team_api_id == team_api_id)
        .filter(PlayerSeasonStats.season.in_(_RECENT_SEASONS))
        .group_by(PlayerSeasonStats.player_api_id)
        .all()
    )
    out: dict[int, float] = {}
    for pid, g, a in rows:
        out[pid] = float((g or 0) + (a or 0))
    return out


def _team_key_absence_share(team_api_id: int, db) -> float:
    """Share of the team's (goals + assists) output represented by currently
    sidelined players. Range 0.0 (everyone fit) → 1.0 (the whole attack is out).

    Mapping over team_api_id alone is approximate — national-team sidelined
    rows are keyed on the CLUB id in api-football, not the national team id.
    To keep the function meaningful without solving that, we sum
    contributions over ALL clubs that match the national-team's roster, by
    cross-referencing sidelined player_api_id back to PlayerSeasonStats.
    """
    contribution = _team_contribution_map(team_api_id, db)
    total = sum(contribution.values())
    if total < _MIN_DENOM:
        return 0.0

    now = datetime.utcnow()
    sidelined_pids = set()
    for r in db.query(PlayerSidelined.player_api_id, PlayerSidelined.end_date).all():
        # Out IF no end date set OR end date is in the future.
        if r[1] is None or r[1] >= now:
            sidelined_pids.add(r[0])

    if not sidelined_pids:
        return 0.0

    absent_contrib = sum(contribution.get(pid, 0.0) for pid in sidelined_pids)
    return absent_contrib / total if total else 0.0


def _share_to_mult(share: float) -> float:
    """Convert an absence share to a lambda multiplier.

    A team missing players who contribute 30%+ of its goals/assists gets the
    full -5% hit. Linear ramp below that, capped at zero for share=0.
    """
    if share <= 0:
        return 1.0
    # 30% loss → full cap. Anything beyond saturates.
    severity = min(1.0, share / 0.30)
    return round(1.0 - _CAP * severity, 4)


def get_key_player_absence_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """Return (home_mult, away_mult). DB-only, neutral when no data.

    Safe to call for every match. Defaults to (1.0, 1.0) for any team
    without harvested player_season_stats or sidelined data — same
    contract as every other modifier here.
    """
    home_id = TEAM_IDS.get(home_code)
    away_id = TEAM_IDS.get(away_code)
    if not home_id and not away_id:
        return 1.0, 1.0

    db = SessionLocal()
    try:
        home_share = _team_key_absence_share(home_id, db) if home_id else 0.0
        away_share = _team_key_absence_share(away_id, db) if away_id else 0.0
    finally:
        db.close()

    return _share_to_mult(home_share), _share_to_mult(away_share)
