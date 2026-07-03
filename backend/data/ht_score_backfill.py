"""Backfill half-time scores into the Match table from existing HarvestRaw blobs.

The api-football `/fixtures` endpoint includes `score.halftime.{home,away}` for
every completed match. We were already harvesting those blobs (4 done — one
per seeded league/season combo) but never pulled the HT data out. This module
walks those blobs once and writes the HT scores into the existing matches
without burning any new API calls.

Idempotent + safe: only updates Match rows where HT is currently NULL and the
team names match. Skips matches that already have HT data so it's cheap to
run as a scheduled job (no churn) and equally cheap on first deploy.
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from backend.db.models import HarvestRaw, Match, MatchEvent, Team
from backend.db.session import SessionLocal
from backend.data.fetchers.injuries import TEAM_IDS

logger = logging.getLogger(__name__)


def _normalise(s: Optional[str]) -> str:
    return (s or "").strip().lower()


def backfill_ht_scores() -> dict:
    """Walk the /fixtures harvest blobs and populate home_ht_score / away_ht_score.

    Returns a small summary so the scheduler wrapper can log it.
    """
    db = SessionLocal()
    try:
        # Cheap full-table scan of /fixtures blobs (there are ~4 of them — one
        # per seeded league/season). Each blob contains hundreds of fixtures.
        raw_rows = (
            db.query(HarvestRaw)
            .filter(HarvestRaw.endpoint == "/fixtures")
            .filter(HarvestRaw.status_code == 200)
            .all()
        )

        # Team-name → code map so we can match api-football's team names against
        # our internal Match.home_code/away_code.
        teams = db.query(Team).all()
        name_to_code = {_normalise(t.name): t.code for t in teams}

        # Index our matches by (home_code, away_code, date_iso) for O(1) lookup.
        match_idx: dict[tuple[str, str, str], Match] = {}
        for m in db.query(Match).all():
            if m.kickoff:
                key = (m.home_code, m.away_code, m.kickoff.date().isoformat())
                match_idx[key] = m

        updated = 0
        skipped_no_match = 0
        skipped_already_set = 0
        skipped_no_ht = 0

        for raw in raw_rows:
            try:
                data = json.loads(raw.response_json or "{}")
            except Exception:
                continue
            for fx in data.get("response") or []:
                score = fx.get("score") or {}
                ht = score.get("halftime") or {}
                ht_home = ht.get("home")
                ht_away = ht.get("away")
                if ht_home is None or ht_away is None:
                    skipped_no_ht += 1
                    continue

                teams_obj = fx.get("teams") or {}
                home_name = ((teams_obj.get("home") or {}).get("name")) or ""
                away_name = ((teams_obj.get("away") or {}).get("name")) or ""
                home_code = name_to_code.get(_normalise(home_name))
                away_code = name_to_code.get(_normalise(away_name))
                if not home_code or not away_code:
                    skipped_no_match += 1
                    continue

                fxd = (fx.get("fixture") or {}).get("date")
                if not fxd:
                    continue
                # api-football date is ISO with timezone — take the date part.
                date_iso = fxd[:10]

                m = match_idx.get((home_code, away_code, date_iso))
                # Also try the reverse — some blobs list the away side as home
                # if the data source flipped them on a neutral venue.
                if m is None:
                    m = match_idx.get((away_code, home_code, date_iso))
                    if m is not None:
                        # Swap to match our home/away orientation.
                        ht_home, ht_away = ht_away, ht_home
                if m is None:
                    skipped_no_match += 1
                    continue

                # Only update when both HT columns are currently NULL — gives
                # operators room to override manually without our backfill
                # clobbering them on the next tick.
                if m.home_ht_score is not None or m.away_ht_score is not None:
                    skipped_already_set += 1
                    continue

                m.home_ht_score = int(ht_home)
                m.away_ht_score = int(ht_away)
                updated += 1

        if updated:
            db.commit()
            logger.info("ht_score_backfill: wrote HT for %d matches", updated)
        return {
            "updated": updated,
            "skipped_already_set": skipped_already_set,
            "skipped_no_match": skipped_no_match,
            "skipped_no_ht": skipped_no_ht,
            "raw_blobs_scanned": len(raw_rows),
        }
    finally:
        db.close()


def backfill_ht_scores_from_events() -> dict:
    """Fallback HT backfill — counts goal events with elapsed <= 45 per team.

    The primary `backfill_ht_scores()` only works for fixtures whose /fixtures
    blob we harvested (currently EPL + Bundesliga 2024 — not WC matches). For
    WC matches we DO have per-minute goal events from the live poller in
    MatchEvent, so we can reconstruct HT scores from them.

    Only writes when:
      - the Match has FT scores (so we trust it's actually complete)
      - the HT columns are still NULL
      - we have at least one goal event for the match OR FT scores are 0-0
        (in which case HT is also 0-0 by definition)
    """
    db = SessionLocal()
    try:
        # Reverse map: api-football team_id → our internal team_code
        api_id_to_code = {v: k for k, v in TEAM_IDS.items()}

        candidates = (
            db.query(Match)
            .filter(Match.status == "complete")
            .filter(Match.home_score.isnot(None), Match.away_score.isnot(None))
            .filter(Match.home_ht_score.is_(None))
            .all()
        )

        updated = 0
        skipped_no_events = 0

        for m in candidates:
            # 0-0 FT shortcut — HT must also be 0-0; no events needed.
            if m.home_score == 0 and m.away_score == 0:
                m.home_ht_score = 0
                m.away_ht_score = 0
                updated += 1
                continue

            events = (
                db.query(MatchEvent)
                .filter(MatchEvent.match_id == m.id)
                .filter(MatchEvent.type == "Goal")
                .filter(MatchEvent.superseded_at.is_(None))
                .all()
            )

            if not events:
                # No event data — leave the row alone. We can't make up HT.
                skipped_no_events += 1
                continue

            home_ht = 0
            away_ht = 0
            for e in events:
                # api-football puts injury-time first-half goals as elapsed=45
                # with extra > 0. Anything elapsed <= 45 counts as first half.
                if e.elapsed is None or e.elapsed > 45:
                    continue
                # Own goals count for the team they helped — `detail` may say
                # "Own Goal" but the team_id on the event is the team CREDITED
                # with the goal (api-football flips it). We trust team_id.
                team_code = api_id_to_code.get(e.team_id)
                if team_code == m.home_code:
                    home_ht += 1
                elif team_code == m.away_code:
                    away_ht += 1

            # Sanity check: HT can't exceed FT. If it does, something is off
            # (missing event, miscoded team_id). Skip to avoid bad data.
            if home_ht > (m.home_score or 0) or away_ht > (m.away_score or 0):
                skipped_no_events += 1
                continue

            m.home_ht_score = home_ht
            m.away_ht_score = away_ht
            updated += 1

        if updated:
            db.commit()
            logger.info("ht_score_backfill (events path): wrote HT for %d matches", updated)
        return {
            "updated_from_events": updated,
            "skipped_no_events": skipped_no_events,
            "candidates_scanned": len(candidates),
        }
    finally:
        db.close()


def backfill_all() -> dict:
    """Run both backfill paths — used by the scheduler. Returns a combined summary."""
    a = backfill_ht_scores()
    b = backfill_ht_scores_from_events()
    return {**a, **b}
