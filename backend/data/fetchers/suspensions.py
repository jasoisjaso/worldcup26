"""
WC2026 suspension tracker.

Reads suspensions.json (in data/overrides/) which maps match_id -> {team_code -> count}.
Returns ELO delta and human-readable why_factor entries for the predictions pipeline.

-40 ELO per suspended player (approx -0.12 expected goals per suspension).
Auto-updated by refresh_match_events() when FOOTBALL_DATA_ORG_KEY is set.
"""
from __future__ import annotations
import json
import os
import pathlib
import logging

import httpx

logger = logging.getLogger(__name__)

# Resolve relative to this module so it works outside the /app Docker layout too;
# override with SUSPENSIONS_PATH if needed.
_SUSP_PATH = pathlib.Path(
    os.getenv("SUSPENSIONS_PATH")
    or (pathlib.Path(__file__).resolve().parent.parent / "overrides" / "suspensions.json")
)
_FDORG_KEY = os.getenv("FOOTBALL_DATA_KEY", "") or os.getenv("FOOTBALL_DATA_ORG_KEY", "")
_FDORG_BASE = "https://api.football-data.org/v4"

# -40 ELO per suspended outfield player (~-0.12 xG)
_ELO_PER_SUSPENSION = -40.0

# football-data.org team TLA -> our team code
_FD_TLA_TO_CODE: dict[str, str] = {
    "MEX": "mx", "RSA": "za", "KOR": "kr", "CZE": "cz",
    "CAN": "ca", "BIH": "ba", "USA": "us", "PAR": "py",
    "QAT": "qa", "SUI": "ch", "BRA": "br", "MAR": "ma",
    "HAI": "ht", "SCO": "gb-sct", "AUS": "au", "TUR": "tr",
    "GER": "de", "CUW": "cw", "NED": "nl", "JPN": "jp",
    "SWE": "se", "TUN": "tn", "BEL": "be", "EGY": "eg",
    "IRN": "ir", "NZL": "nz", "ESP": "es", "CPV": "cv",
    "KSA": "sa", "URU": "uy", "FRA": "fr", "SEN": "sn",
    "IRQ": "iq", "NOR": "no", "ARG": "ar", "ALG": "dz",
    "AUT": "at", "JOR": "jo", "POR": "pt", "COD": "cd",
    "COL": "co", "UZB": "uz", "ENG": "gb-eng", "CRO": "hr",
    "GHA": "gh", "CIV": "ci", "ECU": "ec",
}


def _load() -> dict:
    try:
        return json.loads(_SUSP_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(data: dict) -> None:
    _SUSP_PATH.write_text(json.dumps(data, indent=2))


def get_suspension_count(match_id: str, team_code: str) -> int:
    """How many players are suspended for team_code in this specific match."""
    data = _load()
    entry = data.get(match_id, {})
    return int(entry.get(team_code, 0))


def get_suspension_elo_delta(match_id: str, team_code: str) -> float:
    """ELO penalty for suspended players. Negative value."""
    count = get_suspension_count(match_id, team_code)
    return count * _ELO_PER_SUSPENSION


def get_suspension_why_factors(match_id: str, home_code: str, away_code: str) -> list[dict]:
    """Return why_factor dicts for the predictions 'why_factors' list."""
    factors = []
    home_n = get_suspension_count(match_id, home_code)
    away_n = get_suspension_count(match_id, away_code)
    if home_n:
        s = "player" if home_n == 1 else "players"
        factors.append({
            "label": f"{home_n} {s} suspended (red card from previous match)",
            "direction": "negative",
        })
    if away_n:
        s = "player" if away_n == 1 else "players"
        factors.append({
            "label": f"Opposition down {away_n} {s} (red card suspension)",
            "direction": "positive",
        })
    return factors


async def refresh_match_events(completed_match_ids: list[str] | None = None) -> None:
    """
    Fetch bookings from football-data.org for completed WC2026 matches and
    update suspensions.json with red card suspensions for the following game.

    Requires FOOTBALL_DATA_ORG_KEY. No-op when key is not set.
    """
    if not _FDORG_KEY:
        return

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f"{_FDORG_BASE}/competitions/WC/matches",
                headers={"X-Auth-Token": _FDORG_KEY},
                params={"season": 2026, "status": "FINISHED"},
            )
            if resp.status_code != 200:
                logger.warning("football-data.org returned %s", resp.status_code)
                return
            matches = resp.json().get("matches", [])
    except Exception as exc:
        logger.error("match_events fetch failed: %s", exc)
        return

    # For each finished WC match, find red cards and mark suspended players
    # for the team's next WC match. We do a simple approach: count red cards
    # per team per match, then look up their next fixture in our schedule.
    from backend.db.session import SessionLocal
    from backend.db.models import Match

    db = SessionLocal()
    try:
        # Preserve manual overrides; only update/add entries found from the API
        susp: dict = {k: v for k, v in _load().items() if k != "_note"}
        susp["_note"] = "Auto-updated by refresh_match_events"
        for fd_match in matches:
            bookings = fd_match.get("bookings") or []
            red_cards: dict[str, int] = {}
            for b in bookings:
                if b.get("type") not in ("RED_CARD", "YELLOW_RED_CARD"):
                    continue
                tla = b.get("team", {}).get("tla", "")
                code = _FD_TLA_TO_CODE.get(tla)
                if code:
                    red_cards[code] = red_cards.get(code, 0) + 1

            if not red_cards:
                continue

            # Find the matching WC match in our DB by date + teams
            fd_home_tla = fd_match.get("homeTeam", {}).get("tla", "")
            fd_away_tla = fd_match.get("awayTeam", {}).get("tla", "")
            home_code = _FD_TLA_TO_CODE.get(fd_home_tla)
            away_code = _FD_TLA_TO_CODE.get(fd_away_tla)
            if not home_code or not away_code:
                continue

            our_match = (
                db.query(Match)
                .filter(Match.home_code == home_code, Match.away_code == away_code)
                .first()
            )
            if not our_match:
                continue

            # Find each red-carded team's next WC fixture
            for team_code, count in red_cards.items():
                next_match = (
                    db.query(Match)
                    .filter(
                        Match.status == "upcoming",
                        Match.kickoff > our_match.kickoff,
                        (Match.home_code == team_code) | (Match.away_code == team_code),
                    )
                    .order_by(Match.kickoff)
                    .first()
                )
                if next_match:
                    if next_match.id not in susp:
                        susp[next_match.id] = {}
                    susp[next_match.id][team_code] = count
                    logger.info(
                        "Suspension: %s has %d player(s) out for %s",
                        team_code, count, next_match.id,
                    )

        _save(susp)
        logger.info("Suspensions updated from football-data.org")
    finally:
        db.close()
