"""
Open-Meteo venue weather — match-time conditions multiplier.

Returns (home_mult, away_mult) from the forecast at the venue near kickoff. Open-Meteo is
keyless and free, and its 16-day hourly horizon covers scheduled World Cup fixtures (the old
OpenWeatherMap path needed a key and only reached 5 days, so it was usually inactive).

The feature that matters at a hot, mostly-US summer tournament is HEAT: we read apparent
temperature (feels-like, which already folds in humidity, the WBGT signal), and apply a small
lambda penalty to a cold-climate side in serious heat or a hot-climate side in the cold, plus
a heavy-rain dampener. Falls back to (1.0, 1.0) on any miss.
"""
from __future__ import annotations
from datetime import datetime, timezone

import httpx

_BASE = "https://api.open-meteo.com/v1/forecast"

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
_HOT_CLIMATE = {
    "sa", "qa", "ir", "iq", "jo", "uz",          # AFC hot
    "ma", "sn", "ci", "eg", "dz", "tn", "cd",    # CAF
    "za", "gh", "cv", "ht", "pa", "cw",          # CAF + CONCACAF Caribbean
}

_weather_cache: dict[str, tuple[float, float, float]] = {}  # city → (apparent_temp_c, rain_mm, cached_ts)


def _city_key(venue: str) -> str:
    parts = venue.lower().split(",")
    return parts[-1].strip() if parts else ""


async def get_weather_multipliers(
    home_code: str,
    away_code: str,
    venue: str,
    kickoff: datetime | None,
) -> tuple[float, float]:
    if not venue or not kickoff:
        return 1.0, 1.0

    city = _city_key(venue)
    if city not in _VENUE_COORDS:
        return 1.0, 1.0

    now_ts = datetime.utcnow().timestamp()
    kickoff_ts = kickoff.replace(tzinfo=timezone.utc).timestamp() if kickoff.tzinfo else kickoff.timestamp()

    # Open-Meteo gives 16 days; beyond that no forecast exists.
    if kickoff_ts - now_ts > 16 * 86400 or kickoff_ts < now_ts - 6 * 3600:
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
                    params={
                        "latitude": lat,
                        "longitude": lon,
                        "hourly": "apparent_temperature,temperature_2m,precipitation",
                        "forecast_days": 16,
                        "timezone": "UTC",
                    },
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return 1.0, 1.0

        hourly = data.get("hourly", {})
        times = hourly.get("time", [])
        if not times:
            return 1.0, 1.0
        # Match the forecast hour closest to kickoff (times are UTC ISO strings).
        best_i, best_diff = 0, float("inf")
        for i, t in enumerate(times):
            try:
                ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc).timestamp()
            except ValueError:
                continue
            diff = abs(ts - kickoff_ts)
            if diff < best_diff:
                best_diff, best_i = diff, i

        app_t = hourly.get("apparent_temperature") or hourly.get("temperature_2m") or []
        precip = hourly.get("precipitation") or []
        temp_c = app_t[best_i] if best_i < len(app_t) else None
        rain_mm = precip[best_i] if best_i < len(precip) else 0.0
        if temp_c is None:
            return 1.0, 1.0
        _weather_cache[city] = (temp_c, rain_mm, now_ts)

    home_mult = _conditions_mult(home_code, temp_c, rain_mm)
    away_mult = _conditions_mult(away_code, temp_c, rain_mm)
    return home_mult, away_mult


def _conditions_mult(code: str, app_temp_c: float, rain_mm: float) -> float:
    # app_temp_c is feels-like (apparent temperature), so the thresholds already account for
    # humidity, which is what makes a hot venue actually sap a team.
    mult = 1.0
    if app_temp_c > 32 and code in _COLD_CLIMATE:
        mult *= 0.95   # cold-climate team in serious heat
    elif app_temp_c > 35:
        mult *= 0.97   # extreme heat compresses tempo for everyone
    elif app_temp_c < 6 and code in _HOT_CLIMATE:
        mult *= 0.97   # tropical team in the cold
    # Open-Meteo precipitation is mm for the hour.
    if rain_mm > 3:
        mult *= 0.93   # heavy rain reduces scoring noticeably
    elif rain_mm > 1:
        mult *= 0.97
    return mult
