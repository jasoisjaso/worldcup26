import httpx

WORLDCUP_JSON_URL = (
    "https://raw.githubusercontent.com/openfootball/worldcup.json/master/2026/worldcup.json"
)


async def fetch_wc2026_schedule() -> dict | None:
    """Fetch the 2026 World Cup schedule from openfootball/worldcup.json."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(WORLDCUP_JSON_URL)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
