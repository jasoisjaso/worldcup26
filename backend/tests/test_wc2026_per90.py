"""Tests for the WC2026 per-90 player-stats importer (risingtransfers dataset).

The per90 dataset's player_id is the risingtransfers ID, NOT api-football's, so
the join to our PlayerProfile is by NORMALISED NAME (with slug as a tiebreak).
These tests lock the parse + the name-normalisation that makes the join work.
"""
from __future__ import annotations

from backend.data.importers.wc2026_per90 import (
    normalise_name,
    parse_per90,
)


def test_parses_per90_rows(tmp_path):
    csv = tmp_path / "per90.csv"
    csv.write_text(
        "player_id,player_name,slug,season,minutes,goals_per90,assists_per90,shots_per90,"
        "key_passes_per90,tackles_per90,interceptions_per90,clearances_per90,passes_per90,"
        "pass_accuracy_pct,saves_per90,rating\n"
        "268,Luka Modrić,l-modri,2025-26,2816,0.064,0.096,0.639,1.694,1.662,1.246,1.055,70.92,90.4,0,7.33\n"
    )
    rows = parse_per90(str(csv))
    assert len(rows) == 1
    r = rows[0]
    assert r["name"] == "Luka Modrić"
    assert r["name_key"] == normalise_name("Luka Modrić")
    assert r["slug"] == "l-modri"
    assert r["season"] == "2025-26"
    assert r["minutes"] == 2816
    assert r["goals_per90"] == 0.064
    assert r["assists_per90"] == 0.096
    assert r["rating"] == 7.33


def test_blank_rating_is_none(tmp_path):
    csv = tmp_path / "per90.csv"
    csv.write_text(
        "player_id,player_name,slug,season,minutes,goals_per90,assists_per90,shots_per90,"
        "key_passes_per90,tackles_per90,interceptions_per90,clearances_per90,passes_per90,"
        "pass_accuracy_pct,saves_per90,rating\n"
        "261,Junior Hoilett,d-hoilett,2025-26,722,0.125,0.249,0.62,1.75,1.99,1,0.62,28.17,64.2,0,\n"
    )
    rows = parse_per90(str(csv))
    assert rows[0]["rating"] is None
    assert rows[0]["minutes"] == 722


def test_normalise_name_strips_accents_and_case():
    # Accents removed, lowercased, punctuation collapsed — so "Éder Militão"
    # from our DB matches "Eder Militao" if the dataset spells it plainly.
    assert normalise_name("Éder Militão") == normalise_name("Eder Militao")
    assert normalise_name("Luka Modrić") == "luka modric"
    assert normalise_name("  Neymar  Jr. ") == "neymar jr"
    assert normalise_name("O'Brien") == "obrien"


def test_bad_numeric_fields_dont_crash(tmp_path):
    csv = tmp_path / "per90.csv"
    csv.write_text(
        "player_id,player_name,slug,season,minutes,goals_per90,assists_per90,shots_per90,"
        "key_passes_per90,tackles_per90,interceptions_per90,clearances_per90,passes_per90,"
        "pass_accuracy_pct,saves_per90,rating\n"
        "9,Test Player,test,2025-26,notanum,x,,,,,,,,,,\n"
    )
    rows = parse_per90(str(csv))
    # Row still parses; numeric fields that fail become None/0, name survives.
    assert rows[0]["name"] == "Test Player"
    assert rows[0]["minutes"] == 0
    assert rows[0]["goals_per90"] is None


def test_bundled_per90_lookup_resolves_known_player():
    """The real bundled CSV must load and resolve a well-known player by name."""
    import os
    from backend.data.importers import wc2026_per90 as p90
    if not os.path.exists(p90._BUNDLED_CSV):
        import pytest
        pytest.skip("bundled per-90 dataset not present in this checkout")
    p90._PER90_BY_NAME = {}  # reset the module lookup
    n = p90.ensure_per90_loaded()
    assert n > 1000, f"expected ~1181 per-90 players, got {n}"
    # Modrić is in the dataset; look him up by display name (with the accent).
    rec = p90.get_per90_for_name("Luka Modrić")
    assert rec is not None
    assert rec["minutes"] > 0
    assert rec["goals_per90"] is not None
    # An unknown name returns None, not a crash.
    assert p90.get_per90_for_name("Nobody McNobody") is None
