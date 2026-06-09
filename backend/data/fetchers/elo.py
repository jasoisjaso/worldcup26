import httpx
from bs4 import BeautifulSoup


ELO_URL = "https://www.eloratings.net/World"


async def fetch_elo_ratings() -> list[dict]:
    """Scrape current ELO ratings from eloratings.net."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; WC2026Predictor/1.0)"}
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        response = await client.get(ELO_URL, headers=headers)
        response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    ratings = []

    table = soup.find("table", {"class": "maintable"})
    if not table:
        return ratings

    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 4:
            continue
        try:
            rank = int(cells[0].get_text(strip=True))
            team = cells[1].get_text(strip=True)
            elo = float(cells[3].get_text(strip=True).replace(",", ""))
            ratings.append({"rank": rank, "team_name": team, "elo": elo})
        except (ValueError, IndexError):
            continue

    return ratings
