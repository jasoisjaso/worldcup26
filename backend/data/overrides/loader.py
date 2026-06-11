"""
Key player absence overrides.

Edit key_players.json to apply ELO adjustments when a confirmed star player
is absent. Keys are "{home_code}_{away_code}" (e.g. "jo_dz" for Jordan vs Algeria).

home_elo_delta / away_elo_delta: positive = boost, negative = penalty.
A -100 ELO delta roughly equals -0.3 expected goals for that team.
"""
import json
import pathlib

_PATH = pathlib.Path(__file__).parent / "key_players.json"
_overrides: dict = {}
_loaded = False


def _load() -> dict:
    global _overrides, _loaded
    if not _loaded:
        try:
            _overrides = json.loads(_PATH.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            _overrides = {}
        _loaded = True
    return _overrides


def get_player_overrides(home_code: str, away_code: str) -> tuple[float, float]:
    """Return (home_elo_delta, away_elo_delta) for the given match. 0.0 if no override."""
    overrides = _load()
    key = f"{home_code}_{away_code}"
    entry = overrides.get(key, {})
    return float(entry.get("home_elo_delta", 0.0)), float(entry.get("away_elo_delta", 0.0))
