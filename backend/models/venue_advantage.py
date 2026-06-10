"""
Venue-based ELO adjustments for WC2026.

Three effects:
  1. Host nation bonus — Canada/USA/Mexico playing in their own country.
  2. Diaspora city boost — extra crowd support for Mexico in LA, Dallas, etc.
  3. Altitude penalty — teams from low-altitude countries at Mexico City / Guadalajara.
"""

VENUE_CITY_MAP: dict[str, str] = {
    "mexico city": "Mexico City",
    "guadalajara":  "Guadalajara",
    "monterrey":    "Monterrey",
    "toronto":      "Toronto",
    "vancouver":    "Vancouver",
    "los angeles":  "Los Angeles",
    "dallas":       "Dallas",
    "houston":      "Houston",
    "kansas city":  "Kansas City",
    "new york":     "New York",
    "atlanta":      "Atlanta",
    "philadelphia": "Philadelphia",
    "miami":        "Miami",
    "boston":       "Boston",
    "santa clara":  "Santa Clara",
    "seattle":      "Seattle",
}

# altitude_m: metres above sea level
# host_nation: team code that gets the host bonus
# diaspora_boost: extra ELO for specific team codes (beyond host bonus)
VENUE_DATA: dict[str, dict] = {
    "Mexico City":  {"host": "mx", "altitude_m": 2240, "diaspora": {"mx": 20}},
    "Guadalajara":  {"host": "mx", "altitude_m": 1522, "diaspora": {"mx": 10}},
    "Monterrey":    {"host": "mx", "altitude_m":  538, "diaspora": {}},
    "Toronto":      {"host": "ca", "altitude_m":   76, "diaspora": {}},
    "Vancouver":    {"host": "ca", "altitude_m":   14, "diaspora": {}},
    "Los Angeles":  {"host": "us", "altitude_m":   86, "diaspora": {"mx": 20}},
    "Dallas":       {"host": "us", "altitude_m":  149, "diaspora": {"mx": 15}},
    "Houston":      {"host": "us", "altitude_m":   14, "diaspora": {"mx": 10}},
    "Kansas City":  {"host": "us", "altitude_m":  309, "diaspora": {"mx": 10}},
    "New York":     {"host": "us", "altitude_m":    5, "diaspora": {}},
    "Atlanta":      {"host": "us", "altitude_m":  320, "diaspora": {}},
    "Philadelphia": {"host": "us", "altitude_m":   12, "diaspora": {}},
    "Miami":        {"host": "us", "altitude_m":    1, "diaspora": {"ar": 8, "co": 5, "uy": 5}},
    "Boston":       {"host": "us", "altitude_m":   14, "diaspora": {}},
    "Santa Clara":  {"host": "us", "altitude_m":   17, "diaspora": {"mx": 10}},
    "Seattle":      {"host": "us", "altitude_m":   21, "diaspora": {}},
}

HOST_BONUS: dict[str, int] = {"mx": 65, "ca": 65, "us": 50}
ALTITUDE_CUTOFF = 1500        # metres — above this, altitude matters
ALTITUDE_PENALTY = -20        # applied to non-adapted teams
ALTITUDE_BONUS = 15           # applied to altitude-adapted teams (Mexico, Colombia, Ecuador)
ALTITUDE_ADAPTED = {"mx", "co", "ec"}   # teams whose home base is high altitude
LONG_DISTANCE_PENALTY = -10   # fatigue for teams >10,000 km from home
LONG_DISTANCE_TEAMS = {"nz", "au", "jp", "kr", "uz"}  # >10,000 km to North America


def _parse_city(venue: str) -> str | None:
    """Extract normalised city name from a venue string like 'BMO Field, Toronto'."""
    parts = venue.split(",")
    if len(parts) < 2:
        return None
    city_raw = parts[-1].strip().lower()
    return VENUE_CITY_MAP.get(city_raw)


def get_venue_bonuses(
    home_code: str,
    away_code: str,
    venue: str,
) -> tuple[float, float]:
    """
    Return (home_elo_bonus, away_elo_bonus).
    Positive = advantage, negative = disadvantage.
    """
    city = _parse_city(venue)
    if not city:
        return 0.0, 0.0

    data = VENUE_DATA.get(city)
    if not data:
        return 0.0, 0.0

    home_bonus = 0.0
    away_bonus = 0.0

    host = data["host"]
    alt = data["altitude_m"]
    diaspora = data["diaspora"]

    # Host nation bonus
    if home_code == host:
        home_bonus += HOST_BONUS[host]
    if away_code == host:
        away_bonus += HOST_BONUS[host]

    # Diaspora boost (only for non-host teams that have diaspora there)
    if home_code != host and home_code in diaspora:
        home_bonus += diaspora[home_code]
    if away_code != host and away_code in diaspora:
        away_bonus += diaspora[away_code]

    # Altitude
    if alt >= ALTITUDE_CUTOFF:
        if home_code in ALTITUDE_ADAPTED:
            home_bonus += ALTITUDE_BONUS
        elif home_code != host:
            home_bonus += ALTITUDE_PENALTY

        if away_code in ALTITUDE_ADAPTED:
            away_bonus += ALTITUDE_BONUS
        elif away_code != host:
            away_bonus += ALTITUDE_PENALTY

    # Long-distance fatigue
    if home_code in LONG_DISTANCE_TEAMS:
        home_bonus += LONG_DISTANCE_PENALTY
    if away_code in LONG_DISTANCE_TEAMS:
        away_bonus += LONG_DISTANCE_PENALTY

    return home_bonus, away_bonus
