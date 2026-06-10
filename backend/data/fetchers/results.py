"""Fetch historical international results from martj42/international_results.

Builds a last-5-form cache per team. Refreshed every 6 hours.
Cache is module-level so it survives across requests within one process.
"""
import asyncio
import csv
import io
from datetime import datetime, timedelta

import httpx

RESULTS_CSV_URL = (
    "https://raw.githubusercontent.com/martj42/international_results/master/results.csv"
)

CACHE_TTL = timedelta(hours=6)

# martj42 uses English country names; map them to our ISO codes
_NAME_TO_CODE: dict[str, str] = {
    "Mexico": "mx",
    "South Africa": "za",
    "Czech Republic": "cz",
    "Czechia": "cz",
    "South Korea": "kr",
    "Korea Republic": "kr",
    "Canada": "ca",
    "Bosnia and Herzegovina": "ba",
    "Qatar": "qa",
    "Switzerland": "ch",
    "Brazil": "br",
    "Haiti": "ht",
    "Morocco": "ma",
    "Scotland": "gb-sct",
    "United States": "us",
    "Paraguay": "py",
    "Australia": "au",
    "Turkey": "tr",
    "Germany": "de",
    "Curacao": "cw",
    "Ivory Coast": "ci",
    "Cote d'Ivoire": "ci",
    "Ecuador": "ec",
    "Netherlands": "nl",
    "Japan": "jp",
    "Sweden": "se",
    "Tunisia": "tn",
    "Belgium": "be",
    "Egypt": "eg",
    "Iran": "ir",
    "New Zealand": "nz",
    "Spain": "es",
    "Cape Verde": "cv",
    "Saudi Arabia": "sa",
    "Uruguay": "uy",
    "France": "fr",
    "Senegal": "sn",
    "Iraq": "iq",
    "Norway": "no",
    "Argentina": "ar",
    "Algeria": "dz",
    "Austria": "at",
    "Jordan": "jo",
    "Portugal": "pt",
    "DR Congo": "cd",
    "Colombia": "co",
    "Uzbekistan": "uz",
    "England": "gb-eng",
    "Croatia": "hr",
    "Ghana": "gh",
    "Panama": "pa",
}

_form_cache: dict[str, list[str]] = {}
_cache_built_at: datetime | None = None
_refresh_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _refresh_lock
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
    return _refresh_lock


def _cache_stale() -> bool:
    if _cache_built_at is None:
        return True
    return (datetime.utcnow() - _cache_built_at) > CACHE_TTL


async def refresh_form_cache() -> None:
    global _form_cache, _cache_built_at
    if not _cache_stale():
        return
    async with _get_lock():
        if not _cache_stale():
            return
        try:
            async with httpx.AsyncClient(timeout=25.0) as client:
                resp = await client.get(RESULTS_CSV_URL)
                resp.raise_for_status()
            raw = resp.text
        except Exception:
            return

        team_results: dict[str, list[tuple[str, str]]] = {}
        reader = csv.DictReader(io.StringIO(raw))

        for row in reader:
            date = row.get("date", "")
            home = row.get("home_team", "")
            away = row.get("away_team", "")
            try:
                hs = int(row.get("home_score", ""))
                as_ = int(row.get("away_score", ""))
            except (ValueError, TypeError):
                continue

            home_code = _NAME_TO_CODE.get(home)
            away_code = _NAME_TO_CODE.get(away)

            if home_code:
                r = "W" if hs > as_ else ("D" if hs == as_ else "L")
                team_results.setdefault(home_code, []).append((date, r))

            if away_code:
                r = "W" if as_ > hs else ("D" if hs == as_ else "L")
                team_results.setdefault(away_code, []).append((date, r))

        new_cache: dict[str, list[str]] = {}
        for code, results in team_results.items():
            results.sort(key=lambda x: x[0])
            new_cache[code] = [r for _, r in results[-5:]]

        _form_cache = new_cache
        _cache_built_at = datetime.utcnow()


async def get_recent_form(team_code: str, n: int = 5) -> list[str]:
    if _cache_stale():
        await refresh_form_cache()
    return _form_cache.get(team_code, [])
