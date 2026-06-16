"""Closing Line Value capture.

For each logged pick, snapshot the bookmaker line near kickoff (the sharpest public
estimate) and score the bet price against it. While a match is still in its pre-kickoff
window the closing line is overwritten on each pass so it converges to the true close; once
kickoff passes it is frozen. CLV is filled in only when the market can be de-vigged.

This is measurement only — it does not change which picks are logged. The point is to learn,
within ~100 picks rather than a full season, whether the model's edges actually beat the
market (see README "Better picks" backlog)."""
from __future__ import annotations

from datetime import datetime, timedelta

from backend.betting.market import closing_line_value
from backend.data.fetchers.odds import get_odds_for_match
from backend.db.models import Match, Prediction
from backend.db.session import SessionLocal

# How far ahead of kickoff we start treating the live line as "closing".
_CLOSING_WINDOW_HOURS = 3


async def update_closing_lines() -> None:
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        window_open = now + timedelta(hours=_CLOSING_WINDOW_HOURS)
        preds = db.query(Prediction).all()
        odds_cache: dict[str, dict | None] = {}
        updated = 0
        for p in preds:
            # Per-pick guard so one bad match can't abort the whole pass's commit.
            try:
                m = db.get(Match, p.match_id)
                if not m or not m.kickoff:
                    continue
                # Only ever snapshot a PRE-kickoff line — refreshed each pass so it converges
                # to the true close, then frozen once the match starts. An in-play line is not
                # a closing line, so we never capture after kickoff: better a missing CLV than
                # a wrong one.
                if m.kickoff <= now or m.kickoff > window_open:
                    continue

                if p.match_id not in odds_cache:
                    odds_cache[p.match_id] = await get_odds_for_match(p.match_id)
                book = odds_cache[p.match_id]
                if not book:
                    continue

                close_dec, clv = closing_line_value(p.market, p.bookmaker_odds, book)
                if close_dec is None:
                    continue
                p.closing_odds = close_dec
                if clv is not None:
                    p.clv = clv
                updated += 1
            except Exception as e:  # noqa: BLE001
                print(f"[clv] skipped {p.match_id}/{p.market}: {e}")
        db.commit()
        if updated:
            print(f"[clv] closing lines captured/updated for {updated} pick(s)")
    except Exception as e:  # noqa: BLE001 — never let a scheduler job crash the loop
        print(f"[clv] update failed: {e}")
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(update_closing_lines())
