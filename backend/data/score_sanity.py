"""Permanent sanity check on stored Match scores vs MatchEvent goal totals.

Why this exists: 2026-06-21 we found 6 WC matches with wrong FT scores in
the DB. Root cause was the Odds API path matching teams across a wide
`daysFrom` window, which silently picked up a HISTORICAL friendly between
the same teams (Haiti 1-0 Scotland from years ago) and overwrote our
WC2026 Match row with the wrong score. The fix is two-layer:

  1. This audit runs on a scheduler tick. For every completed match it
     compares the stored FT to the goal events captured by the live
     poller (which is trustworthy — keyed by api_fixture_id + minute).
     - When stored is the SWAP of events with matching totals: auto-fix.
       Safe: preserves the magnitude, only flips orientation.
     - When stored disagrees in magnitude: log an ALERT. Don't auto-fix —
       events may be incomplete (live poller missed a goal). Surface to
       the operator via the harvester error log + Sentry.

  2. The score writer in `backend/data/fetchers/scores.py` should gate by
     kickoff window (a fix tracked separately) so the underlying race
     stops happening. This audit is the belt-and-braces.

Idempotent: only writes when stored differs from a swap-match. Never
auto-corrects the magnitude case (events could be incomplete).
"""
from __future__ import annotations

import logging
from collections import Counter

from backend.data.fetchers.injuries import TEAM_IDS
from backend.data.persistence import is_shootout_event
from backend.db.models import HarvestErrorLog, Match, MatchEvent
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)


def audit_match_scores() -> dict:
    """Walk completed matches, compare stored vs events, auto-fix swaps.

    Returns a summary dict for the scheduler to log + the admin to surface.
    """
    db = SessionLocal()
    api_to_code = {v: k for k, v in TEAM_IDS.items()}

    ok = swap_fixed = mismatched = skipped_no_events = 0
    alerts: list[dict] = []

    try:
        completed = (
            db.query(Match)
            .filter(Match.status == "complete")
            .filter(Match.home_score.isnot(None), Match.away_score.isnot(None))
            .all()
        )
        for m in completed:
            events = (
                db.query(MatchEvent)
                .filter(MatchEvent.match_id == m.id)
                .filter(MatchEvent.superseded_at.is_(None))
                .all()
            )
            # "type == Goal" alone over-counts three ways (all hit in prod and
            # buried the real M075 corruption under alert noise, 2026-07-04):
            #   - detail="Missed Penalty" rides on type="Goal",
            #   - shootout kicks are type="Goal" at 120' (M088: 6-5 vs true 1-1),
            #   - VAR-disallowed goals stay in the insert-only archive; the
            #     Var event that cancels them is the only tombstone.
            var_disallowed = {
                (e.elapsed, e.player_id)
                for e in events
                if e.type == "Var" and e.detail and e.player_id and e.elapsed is not None
                and ("disallowed" in e.detail.lower()
                     or "cancelled" in e.detail.lower()
                     or "canceled" in e.detail.lower())
            }
            goal_events = [
                e for e in events
                if e.type == "Goal"
                and (e.detail or "") != "Missed Penalty"
                and not is_shootout_event(e.elapsed, e.extra, e.comments)
                and (e.elapsed, e.player_id) not in var_disallowed
            ]
            if not goal_events:
                skipped_no_events += 1
                continue

            by_id = Counter(e.team_id for e in goal_events)
            home_ev = sum(c for tid, c in by_id.items() if api_to_code.get(tid) == m.home_code)
            away_ev = sum(c for tid, c in by_id.items() if api_to_code.get(tid) == m.away_code)
            unmapped = sum(c for tid, c in by_id.items() if api_to_code.get(tid) is None)

            stored = (m.home_score or 0, m.away_score or 0)
            from_events = (home_ev, away_ev)

            if stored == from_events:
                ok += 1
                continue

            # Swap test: stored is the orientation-flipped version of events.
            # When (home_stored, away_stored) == (away_ev, home_ev), the stored
            # row has the score labels swapped relative to events. Fix by
            # writing the EVENT-derived orientation (home_ev, away_ev) — that
            # IS the correct value, since events are keyed by team_id (no
            # ambiguity), unlike the stored score which came from a fuzzy
            # team-name match in the Odds API.
            if stored == (away_ev, home_ev):
                m.home_score, m.away_score = home_ev, away_ev
                # Clear HT scores so the HT backfill re-derives them against
                # the corrected FT (preserves the "HT can't exceed FT" guard).
                m.home_ht_score = None
                m.away_ht_score = None
                swap_fixed += 1
                logger.warning(
                    "score_sanity AUTOFIX-SWAP %s: stored %d-%d -> %d-%d (events confirm orientation)",
                    m.id, stored[0], stored[1], home_ev, away_ev,
                )
                # Diagnostic trail in the HarvestErrorLog so we have a record.
                db.add(HarvestErrorLog(
                    job_id=None,
                    endpoint="score_sanity:autofix",
                    error_type="orientation_swap",
                    error_msg=f"{m.id} {stored[0]}-{stored[1]} -> {home_ev}-{away_ev}",
                ))
                continue

            # Magnitude disagrees with events. Don't auto-fix — events might
            # be incomplete (live poller missed a goal during a network blip).
            # Log an alert for operator review.
            mismatched += 1
            alert = {
                "match_id": m.id,
                "home_code": m.home_code,
                "away_code": m.away_code,
                "stored": stored,
                "from_events": from_events,
                "unmapped_event_goals": unmapped,
            }
            alerts.append(alert)
            logger.error(
                "score_sanity MISMATCH %s: stored %d-%d vs events %d-%d (unmapped: %d)",
                m.id, stored[0], stored[1], home_ev, away_ev, unmapped,
            )
            db.add(HarvestErrorLog(
                job_id=None,
                endpoint="score_sanity:alert",
                error_type="score_event_mismatch",
                error_msg=f"{m.id} stored={stored} events={from_events} unmapped={unmapped}",
            ))

        if swap_fixed or mismatched:
            db.commit()
            # Re-run HT backfill so the swapped matches get HT re-derived
            # against the corrected FT.
            if swap_fixed:
                from backend.data.ht_score_backfill import backfill_ht_scores_from_events
                backfill_ht_scores_from_events()
    finally:
        db.close()

    return {
        "ok": ok,
        "swap_fixed": swap_fixed,
        "mismatched": mismatched,
        "skipped_no_events": skipped_no_events,
        "alerts": alerts,
    }
