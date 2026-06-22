"""Importer for the WC2026 squad-value open dataset.

Source: risingtransfers/world-cup-2026-data  (data/squads.csv), CC BY 4.0.
  https://github.com/risingtransfers/world-cup-2026-data
  Attribution: Squad values — Rising Transfers (risingtransfers.com), CC BY 4.0.

Why: backend/data/fetchers/squad_values.py shipped with a DEAD Transfermarkt
scraper (a no-op parse loop), so the squad-quality lambda modifier always ran
on a hand-typed pre-tournament static table. This dataset is a WC-exact,
licensed, attributable replacement — 1,363 players with an AI transfer-value
estimate (EUR) per player. We aggregate to a total squad value per nation and
feed it into the existing ±8% multiplier, unchanged.

The dataset's `country_code` column is a clean FIFA 3-letter code, so the
nation→our-internal-code mapping is a deterministic lookup (no fuzzy matching).
"""
from __future__ import annotations

import csv

# FIFA 3-letter code (from the dataset's country_code column) → our internal
# team code (from the Team table). Verified against the live dataset's 48
# nations and the live Team table on 2026-06-22.
FIFA_TO_CODE: dict[str, str] = {
    # UEFA
    "FRA": "fr", "ESP": "es", "POR": "pt", "GER": "de", "NED": "nl",
    "BEL": "be", "ENG": "gb-eng", "CRO": "hr", "SUI": "ch", "TUR": "tr",
    "AUT": "at", "NOR": "no", "CZE": "cz", "SCO": "gb-sct", "BIH": "ba",
    "SWE": "se",
    # CONMEBOL
    "ARG": "ar", "BRA": "br", "COL": "co", "URU": "uy", "ECU": "ec",
    "PRY": "py",
    # AFC
    "JPN": "jp", "IRN": "ir", "KOR": "kr", "AUS": "au", "KSA": "sa",
    "UZB": "uz", "QAT": "qa", "JOR": "jo", "IRQ": "iq",
    # CONCACAF
    "MEX": "mx", "USA": "us", "CAN": "ca", "PAN": "pa", "CUW": "cw",
    "HTI": "ht",
    # CAF
    "MAR": "ma", "SEN": "sn", "CIV": "ci", "EGY": "eg", "DZA": "dz",
    "TUN": "tn", "COD": "cd", "ZAF": "za", "GHA": "gh", "CPV": "cv",
    # OFC
    "NZL": "nz",
}


def aggregate_values(csv_path: str) -> dict[str, float]:
    """Read the squads CSV and return {our_team_code: total_value_millions_eur}.

    - Sums `rt_value_estimate_eur` over every player of a nation.
    - Converts to millions (the unit STATIC_VALUES + the multiplier expect).
    - Skips rows with an unmapped country code or a missing/non-numeric value.
    """
    totals: dict[str, float] = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = FIFA_TO_CODE.get((row.get("country_code") or "").strip().upper())
            if not code:
                continue
            raw = (row.get("rt_value_estimate_eur") or "").strip()
            if not raw:
                continue
            try:
                value_eur = float(raw)
            except (ValueError, TypeError):
                continue
            totals[code] = totals.get(code, 0.0) + value_eur

    # Convert EUR → millions EUR, rounded to match the STATIC_VALUES scale.
    return {code: round(total / 1_000_000.0, 1) for code, total in totals.items()}
