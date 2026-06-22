"""Tests for the WC2026 squad-value importer (risingtransfers dataset).

The dataset's `country_code` is a clean FIFA 3-letter code (SCO, CAN, CIV...),
so the nation→our-code mapping is a deterministic lookup, not fuzzy matching.
These tests lock the aggregation math and the mapping of the tricky codes.
"""
from __future__ import annotations

from backend.data.importers.wc2026_squad_values import (
    FIFA_TO_CODE,
    aggregate_values,
)


def test_aggregates_squad_value_by_nation(tmp_path):
    csv = tmp_path / "squads.csv"
    csv.write_text(
        "player_id,player_name,slug,country,country_code,position,club,age,rt_value_estimate_eur\n"
        "1,A,a,France,FRA,FW,PSG,24,180000000\n"
        "2,B,b,France,FRA,DF,Madrid,28,60000000\n"
        "3,C,c,Haiti,HTI,MF,MLS,22,2000000\n"
    )
    out = aggregate_values(str(csv))
    # Summed per nation, converted to millions EUR.
    assert out["fr"] == 240.0   # (180m + 60m)
    assert out["ht"] == 2.0


def test_maps_every_tricky_fifa_code(tmp_path):
    """The codes that don't trivially match our internal scheme must all resolve."""
    tricky = {
        "SCO": "gb-sct", "ENG": "gb-eng", "CIV": "ci", "KOR": "kr",
        "USA": "us", "COD": "cd", "CUW": "cw", "CPV": "cv", "TUR": "tr",
        "NED": "nl", "GER": "de", "KSA": "sa", "ZAF": "za", "PRY": "py",
        "BIH": "ba", "CZE": "cz",
    }
    for fifa, ours in tricky.items():
        assert FIFA_TO_CODE.get(fifa) == ours, f"{fifa} should map to {ours}"


def test_all_48_fifa_codes_covered():
    """Every WC nation in the dataset must have a mapping (no silent drops)."""
    dataset_fifa = {
        "DZA", "ARG", "AUS", "AUT", "BEL", "BIH", "BRA", "CAN", "CPV", "COL",
        "COD", "CRO", "CUW", "CZE", "CIV", "ECU", "EGY", "ENG", "FRA", "GER",
        "GHA", "HTI", "IRN", "IRQ", "JPN", "JOR", "KOR", "MEX", "MAR", "NED",
        "NZL", "NOR", "PAN", "PRY", "POR", "QAT", "KSA", "SCO", "SEN", "ZAF",
        "ESP", "SWE", "SUI", "TUN", "TUR", "USA", "URU", "UZB",
    }
    missing = dataset_fifa - set(FIFA_TO_CODE)
    assert not missing, f"unmapped FIFA codes: {sorted(missing)}"


def test_unknown_code_is_skipped(tmp_path):
    """A row with an unmapped country code is skipped, not crashed on."""
    csv = tmp_path / "squads.csv"
    csv.write_text(
        "player_id,player_name,slug,country,country_code,position,club,age,rt_value_estimate_eur\n"
        "1,A,a,Atlantis,ATL,FW,Nowhere,24,5000000\n"
        "2,B,b,France,FRA,FW,PSG,24,180000000\n"
    )
    out = aggregate_values(str(csv))
    assert "fr" in out and out["fr"] == 180.0
    assert len(out) == 1  # the bogus nation was dropped


def test_blank_or_bad_value_rows_ignored(tmp_path):
    csv = tmp_path / "squads.csv"
    csv.write_text(
        "player_id,player_name,slug,country,country_code,position,club,age,rt_value_estimate_eur\n"
        "1,A,a,France,FRA,FW,PSG,24,\n"           # blank value
        "2,B,b,France,FRA,DF,Madrid,28,notanum\n"  # non-numeric
        "3,C,c,France,FRA,MF,Lyon,24,90000000\n"   # good
    )
    out = aggregate_values(str(csv))
    assert out["fr"] == 90.0  # only the valid row counts


# --- wiring into squad_values.py -------------------------------------------

def test_imported_values_drive_the_multiplier(monkeypatch):
    """When imported values are loaded, the quality multiplier must use them,
    not the static fallback. A bigger value gap → a bigger (capped) edge."""
    from backend.data.fetchers import squad_values as sv

    # Inject imported values where home is 10x away → should hit the +8% cap.
    monkeypatch.setattr(sv, "_cache", {"fr": 800.0, "ht": 80.0})
    h, a = sv.get_squad_quality_multipliers("fr", "ht")
    assert h > 1.0 and a < 1.0
    assert abs((h - 1.0) - sv._SV_SCALE) < 1e-6, "10x gap should reach the +8% cap"
    assert abs((1.0 - a) - sv._SV_SCALE) < 1e-6


def test_falls_back_to_static_when_no_cache(monkeypatch):
    """With no imported cache, STATIC_VALUES still drives the multiplier (no crash)."""
    from backend.data.fetchers import squad_values as sv
    monkeypatch.setattr(sv, "_cache", {})
    h, a = sv.get_squad_quality_multipliers("fr", "ht")  # both in STATIC_VALUES
    assert h > 1.0 and a < 1.0


def test_load_imported_values_populates_cache(tmp_path, monkeypatch):
    """load_imported_squad_values() reads the CSV into the module cache."""
    from backend.data.fetchers import squad_values as sv
    csv = tmp_path / "squads.csv"
    csv.write_text(
        "player_id,player_name,slug,country,country_code,position,club,age,rt_value_estimate_eur\n"
        "1,A,a,France,FRA,FW,PSG,24,300000000\n"
        "2,C,c,Haiti,HTI,MF,MLS,22,30000000\n"
    )
    monkeypatch.setattr(sv, "_cache", {})
    n = sv.load_imported_squad_values(str(csv), min_nations=2)
    assert n == 2
    assert sv._cache["fr"] == 300.0
    assert sv._cache["ht"] == 30.0


def test_bundled_dataset_loads_all_48_nations(monkeypatch):
    """The real bundled CSV that ships in the image must load all 48 WC nations.
    This is the integration guard: if the dataset file is missing or the schema
    drifts, this fails instead of silently falling back to the stale table."""
    import os
    from backend.data.fetchers import squad_values as sv
    if not os.path.exists(sv._BUNDLED_CSV):
        import pytest
        pytest.skip("bundled dataset not present in this checkout")
    monkeypatch.setattr(sv, "_cache", {})
    n = sv.ensure_squad_values_loaded()
    assert n == 48, f"expected 48 nations from the bundled dataset, got {n}"
    # Sanity: a big nation should outvalue a small one, so the multiplier favours it.
    h, a = sv.get_squad_quality_multipliers("fr", "ht")
    assert h > 1.0 and a < 1.0
