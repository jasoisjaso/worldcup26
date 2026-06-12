"""
OpenWeatherMap venue weather — match-time conditions multiplier.

Returns (home_mult, away_mult) based on temperature and precipitation
at the match venue near kickoff time. Teams poorly adapted to the
conditions take a small lambda penalty.

Falls back to (1.0, 1.0) if OPENWEATHER_API_KEY is not set, venue is
unknown, or kickoff is more than 5 days away (outside free forecast window).
"""
from __future__ import annotations
import os
from datetime import datetime, timezone

import httpx

_API_KEY = os.getenv("OPENWEATHER_API_KEY", "")
_BASE = "https://api.openweathermap.org/data/2.5/forecast"

# WC2026 venue coordinates — (lat, lon) — city key matches _city_key() output
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

# Climate tags — teams who suffer in heat or cold
_COLD_CLIMATE = {"no", "gb-sct", "se", "cz", "at"}
_HOT_CLIMATE  = {
    "sa", "qa", "ir", "iq", "jo", "uz",          # AFC hot
    "ma", "sn", "ci", "eg", "dz", "tn", "cd",    # CAF
    "za", "gh", "cv", "ht", "pa", "cw",           # CAF + CONCACAF Caribbean
}

_weather_cache: dict[str, tuple[float, float, float]] = {}  # city → (temp, rain, cached_ts)


def _city_key(venue: str) -> str:
    parts = venue.lower().split(",")
    return parts[-1].strip() if parts else ""


async def get_weather_multipliers(
    home_code: str,
    away_code: str,
    venue: str,
    kickoff: datetime | None,
) -> tuple[float, float]:
    if not _API_KEY or not venue or not kickoff:
        return 1.0, 1.0

    city = _city_key(venue)
    if city not in _VENUE_COORDS:
        return 1.0, 1.0

    now_ts = datetime.utcnow().timestamp()
    kickoff_ts = kickoff.replace(tzinfo=timezone.utc).timestamp() if kickoff.tzinfo else kickoff.timestamp()

    # Only forecast API covers next ~5 days; beyond that return neutral
    if kickoff_ts - now_ts > 5 * 86400:
        return 1.0, 1.0

    cached = _weather_cache.get(city)
    if cached and now_ts - cached[2] < 3600:
        temp_c, rain_mm = cached[0], cached[1]
    else:
        lat, lon = _VENUE_COORDS[city]
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    _BASE,
                    params={"lat": lat, "lon": lon, "appid": _API_KEY, "units": "metric"},
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return 1.0, 1.0

        best = None
        best_diff = float("inf")
        for item in data.get("list", []):
            diff = abs(item["dt"] - kickoff_ts)
            if diff < best_diff:
                best_diff = diff
                best = item

        if not best:
            return 1.0, 1.0

        temp_c  = best["main"]["temp"]
        rain_mm = best.get("rain", {}).get("3h", 0.0)
        _weather_cache[city] = (temp_c, rain_mm, now_ts)

    home_mult = _conditions_mult(home_code, temp_c, rain_mm)
    away_mult = _conditions_mult(away_code, temp_c, rain_mm)
    return home_mult, away_mult


def _conditions_mult(code: str, temp_c: float, rain_mm: float) -> float:
    mult = 1.0
    if temp_c > 32 and code in _COLD_CLIMATE:
        mult *= 0.95   # cold-climate team in serious heat
    elif temp_c > 34:
        mult *= 0.97   # extreme heat hurts everyone
    elif temp_c < 7 and code in _HOT_CLIMATE:
        mult *= 0.97   # tropical team in cold conditions
    if rain_mm > 8:
        mult *= 0.93   # heavy rain reduces scoring noticeably
    elif rain_mm > 3:
        mult *= 0.97
    return mult
