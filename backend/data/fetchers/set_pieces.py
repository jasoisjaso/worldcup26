"""
Set piece threat index for WC2026 national teams.

Sourced from WC2022, Euro 2024, and Nations League 2024/25 data.
Two indices per team on a -0.5 to +0.5 scale, centred at 0:
  sp_attack  - offensive set piece threat (corners, FKs into the box)
  sp_defense - quality of defending opponent set pieces

Lambda effect:
  home_mult += (sp_attack[home] - sp_defense[away]) * 0.05  → max ±2.5%
  away_mult += (sp_attack[away] - sp_defense[home]) * 0.05  → max ±2.5%

Effect is deliberately small — set pieces shift margins, not outcomes.
"""
from __future__ import annotations

# (sp_attack, sp_defense) per ISO 3166-1 alpha-2 / FIFA code
# Default: (0.0, 0.0) for unlisted nations
_SET_PIECE_DATA: dict[str, tuple[float, float]] = {
    # UEFA
    "gb-eng": ( 0.40,  0.20),   # ~38% goals from set pieces; excellent from corners
    "de":     ( 0.30,  0.25),   # Rüdiger/Tah headers; tight defensive shape
    "nl":     ( 0.30,  0.20),   # Van Dijk corners; organized defending
    "fr":     ( 0.15,  0.15),   # Konate/Camavinga threat; decent structure
    "be":     ( 0.10,  0.10),
    "pt":     ( 0.10,  0.10),   # Ronaldo FKs; mostly open-play focused
    "es":     (-0.20,  0.10),   # Tiki-taka: rarely uses set pieces aggressively
    "hr":     ( 0.10,  0.10),   # Lovren/Gvardiol decent headers
    "ch":     ( 0.05,  0.05),
    "at":     ( 0.10,  0.05),
    "no":     ( 0.20,  0.20),   # Aerial presence, strong at defending
    "se":     ( 0.15,  0.15),   # Historic set piece strength
    "cz":     ( 0.10,  0.05),
    "tr":     ( 0.05,  0.00),
    "gb-sct": ( 0.20,  0.05),   # Direct, set-piece heavy under Clarke
    "ba":     ( 0.10,  0.00),
    # CONMEBOL
    "ar":     ( 0.05,  0.05),   # Messi FKs but generally open-play
    "br":     (-0.10,  0.00),   # Flair-based, not set-piece dependent
    "uy":     ( 0.25,  0.15),   # Physical, aerial threats (Nunez, Araujo)
    "co":     ( 0.00,  0.00),
    "ec":     ( 0.05,  0.05),
    "py":     ( 0.00, -0.05),
    # AFC
    "jp":     (-0.20,  0.05),   # Small squad; physical disadvantage at set pieces
    "kr":     (-0.15,  0.05),
    "au":     ( 0.10,  0.00),   # Tall strikers (Maclaren), decent from corners
    "ir":     ( 0.05,  0.10),   # Organized, well-structured defending
    "sa":     (-0.10, -0.05),
    "uz":     ( 0.00,  0.00),
    "qa":     (-0.15, -0.05),
    "jo":     (-0.05,  0.00),
    "iq":     (-0.10, -0.10),
    # CONCACAF
    "us":     ( 0.20,  0.10),   # Athletic squad, good from dead balls
    "mx":     ( 0.00,  0.05),
    "ca":     ( 0.15,  0.05),   # David, Larin headers
    "pa":     (-0.05, -0.05),
    "cw":     (-0.15, -0.10),
    "ht":     (-0.20, -0.20),
    # CAF
    "ma":     ( 0.00,  0.30),   # Exceptional set piece DEFENCE (WC2022 standout)
    "sn":     ( 0.10,  0.10),   # Kouyate, Jackson threats
    "ci":     ( 0.05,  0.05),
    "eg":     ( 0.05,  0.10),   # Salah FKs; disciplined defensive shape
    "dz":     ( 0.00,  0.05),
    "tn":     (-0.05,  0.05),
    "cd":     ( 0.00,  0.00),
    "za":     (-0.05, -0.05),
    "gh":     ( 0.05, -0.05),
    "cv":     (-0.10, -0.10),
    # OFC
    "nz":     ( 0.00, -0.10),
}

_SP_SCALE = 0.05   # 1 unit difference → 5% lambda change
_SP_CAP = 0.025    # max ±2.5% per team


def get_set_piece_multipliers(home_code: str, away_code: str) -> tuple[float, float]:
    """
    Return (home_mult, away_mult) based on set piece threat mismatch.
    Positive effect when a team's set piece attack faces a weak set piece defence.
    """
    h_atk, h_def = _SET_PIECE_DATA.get(home_code, (0.0, 0.0))
    a_atk, a_def = _SET_PIECE_DATA.get(away_code, (0.0, 0.0))

    net_home = h_atk - a_def   # home attacks vs away's defensive quality
    net_away = a_atk - h_def

    home_adj = max(-_SP_CAP, min(_SP_CAP, net_home * _SP_SCALE))
    away_adj = max(-_SP_CAP, min(_SP_CAP, net_away * _SP_SCALE))

    return round(1.0 + home_adj, 4), round(1.0 + away_adj, 4)
