"""Tests for per-book line-shopping + arbitrage (pure helpers, no network)."""

from backend.data.fetchers.odds import (
    _extract_per_book,
    _best_book,
    _median,
    match_arbitrage,
)


def _event(books):
    """Build a minimal Odds API event with the given {book: {market_key: [outcomes]}}."""
    return {
        "home_team": "France",
        "away_team": "Mexico",
        "bookmakers": [
            {
                "key": book,
                "last_update": "2026-06-16T10:00:00Z",
                "markets": markets,
            }
            for book, markets in books.items()
        ],
    }


def test_median_basic():
    assert _median([2.0, 2.5, 3.0]) == 2.5
    assert _median([2.0, 3.0]) == 3.0  # upper-mid on even count (matches existing behaviour)
    assert _median([]) is None


def test_best_book_picks_longest_price():
    books = {"bet365": 2.10, "sportsbet": 2.35, "unibet": 2.20}
    price, book = _best_book(books)
    assert price == 2.35 and book == "sportsbet"


def test_extract_per_book_keeps_all_three_prices():
    ev = _event({
        "bet365":   [{"key": "h2h", "outcomes": [
            {"name": "France", "price": 1.90}, {"name": "Draw", "price": 3.4}, {"name": "Mexico", "price": 4.2}]}],
        "sportsbet": [{"key": "h2h", "outcomes": [
            {"name": "France", "price": 2.05}, {"name": "Draw", "price": 3.3}, {"name": "Mexico", "price": 4.0}]}],
    })
    per_book = _extract_per_book(ev, swap_home_away=False)
    assert set(per_book["home_win"].keys()) == {"bet365", "sportsbet"}
    assert per_book["home_win"]["sportsbet"]["price"] == 2.05
    # best price for home is the bigger of the two
    price, book = _best_book({b: d["price"] for b, d in per_book["home_win"].items()})
    assert price == 2.05 and book == "sportsbet"


def test_extract_per_book_swaps_home_away():
    ev = _event({"bet365": [{"key": "h2h", "outcomes": [
        {"name": "France", "price": 1.90}, {"name": "Draw", "price": 3.4}, {"name": "Mexico", "price": 4.2}]}]})
    per_book = _extract_per_book(ev, swap_home_away=True)
    # France is the event home, but DB has them away -> France price lands on away_win
    assert per_book["away_win"]["bet365"]["price"] == 1.90
    assert per_book["home_win"]["bet365"]["price"] == 4.2


def test_arbitrage_detects_sure_bet_across_books():
    # Best prices: home 2.1 (A), draw 4.0 (B), away 4.5 (A) -> 1/2.1+1/4.0+1/4.5 = 0.476+0.25+0.222 = 0.948 < 1
    book_odds = {
        "home_win": {"books": {"A": 2.10, "B": 2.0}, "best_price": 2.10, "best_book": "A"},
        "draw":     {"books": {"A": 3.6, "B": 4.0}, "best_price": 4.0, "best_book": "B"},
        "away_win": {"books": {"A": 4.5, "B": 4.2}, "best_price": 4.5, "best_book": "A"},
    }
    arb = match_arbitrage(book_odds, ("home_win", "draw", "away_win"))
    assert arb is not None
    assert arb["margin"] > 0
    assert round(arb["sum_implied"], 3) == 0.948


def test_no_arbitrage_on_normal_market():
    book_odds = {
        "home_win": {"best_price": 1.9}, "draw": {"best_price": 3.3}, "away_win": {"best_price": 4.0},
    }
    arb = match_arbitrage(book_odds, ("home_win", "draw", "away_win"))
    assert arb is None  # sum of implied > 1 (the bookmaker margin)
