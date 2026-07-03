"""Event-trigger dispatcher for the follow-match notification layer.

Runs every ~60s via the refresh scheduler. Reads from MatchEvent,
LiveMatchState and Match; writes to NotificationEventLog (the dedup
gate) and calls push.send_push() with a recipients allowlist.

Decoupled from backend/data/fetchers/live.py — that file is shared
with the shootout-tracking agent. The dispatcher polls the data
fetcher's output, never edits it.

Confirm-queue for goal events (FotMob bug mitigation): goal MatchEvent
rows < GOAL_CONFIRM_DELAY_SECONDS old are skipped on this pass. The
next pass picks them up if they're still in the same shape. Worst-case
notification lag for goals: ~90s. Mis-attribution rate falls because
api-football usually fixes player_id within the first ~30s.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from backend.data import push_events as pe
from backend.db.models import (
    FollowedMatch,
    FollowedTeam,
    LiveMatchState,
    Match,
    MatchEvent,
    NotificationEventLog,
    Team,
)
from backend.db.session import SessionLocal

logger = logging.getLogger(__name__)


# A goal event must be at least this old before we notify. Buys time for
# api-football to correct a wrong player_id (FotMob's published bug — see
# docs/research/2026-06-23 §2b).
GOAL_CONFIRM_DELAY_SECONDS = 30

# How far back to scan MatchEvent on every pass. Cheap with the existing
# (match_id) index; bounded by the live-window so we never re-scan
# yesterday's matches. 6h is plenty even for the longest knockout match.
EVENT_LOOKBACK_HOURS = 6


# ---------------------------------------------------------------------------
# Recipient resolution
# ---------------------------------------------------------------------------


def _endpoints_for(
    db,
    match: Match,
    event_bit: Optional[int],
    event_type: str,
) -> list[str]:
    """Union of (FollowedMatch with bit set) + (FollowedTeam for either
    side with bit set). For ALWAYS_ON events (suspended / resumed) the
    bit check is bypassed — those notify every follower regardless of
    their event_mask, by design.
    """
    is_always_on = event_type in pe.ALWAYS_ON_EVENTS

    fm_q = db.query(FollowedMatch.endpoint).filter(
        FollowedMatch.match_id == match.id
    )
    if not is_always_on and event_bit is not None:
        fm_q = fm_q.filter(FollowedMatch.event_mask.op("&")(event_bit) != 0)
    else:
        # Always-on events still skip the no_auto_refollow stubs (mask=0).
        fm_q = fm_q.filter(FollowedMatch.event_mask > 0)

    ft_q = db.query(FollowedTeam.endpoint).filter(
        FollowedTeam.team_code.in_([match.home_code, match.away_code])
    )
    if not is_always_on and event_bit is not None:
        ft_q = ft_q.filter(FollowedTeam.event_mask.op("&")(event_bit) != 0)

    # Union via set; one DB query each.
    seen = set()
    for (ep,) in fm_q.all():
        seen.add(ep)
    for (ep,) in ft_q.all():
        seen.add(ep)
    return list(seen)


# ---------------------------------------------------------------------------
# Event dispatch — one helper per event type, all share _fire()
# ---------------------------------------------------------------------------


def _already_fired(db, event_key: str) -> bool:
    return (
        db.query(NotificationEventLog)
        .filter(NotificationEventLog.event_key == event_key)
        .first()
        is not None
    )


def _fire(
    db,
    *,
    match: Match,
    event_type: str,
    event_key: str,
    event_bit: Optional[int],
    title: str,
    body: str,
) -> int:
    """Send the notification + log. Returns count of recipients (0 if no
    one followed, in which case we still log to keep the dedup gate honest
    — otherwise the same event re-checks every pass).
    """
    if _already_fired(db, event_key):
        return 0

    endpoints = _endpoints_for(db, match, event_bit, event_type)

    # Import here to avoid a circular import (push.py imports from
    # backend.data via the bitmask module).
    from backend.api.routes.push import send_push

    res = send_push(
        db,
        title=title,
        body=body,
        url=f"/match/{match.id}",
        recipients=endpoints,
    )
    sent = res.get("sent", 0)
    log = NotificationEventLog(
        match_id=match.id,
        event_type=event_type,
        event_key=event_key,
        recipients=sent,
        title=title,
        body=body,
    )
    db.add(log)
    db.commit()
    logger.info(
        "push.dispatch %s match=%s key=%s recipients=%d sent=%d",
        event_type, match.id, event_key, len(endpoints), sent,
    )
    return sent


def _team_name(db, code: str | None) -> str:
    if not code:
        return ""
    t = db.get(Team, code)
    return t.name if t else code.upper()


def _scoreline(match: Match, lms: Optional[LiveMatchState]) -> str:
    if lms and lms.home_score is not None and lms.away_score is not None:
        return f"{lms.home_score}-{lms.away_score}"
    if match.home_score is not None and match.away_score is not None:
        return f"{match.home_score}-{match.away_score}"
    return "0-0"


# ---------------------------------------------------------------------------
# Per-event dispatchers — each examines DB state, fires if appropriate
# ---------------------------------------------------------------------------


def _dispatch_goals_and_cards_and_var(db, match: Match) -> None:
    """Iterate MatchEvent rows for a live/recent match. Fires goal /
    red_card / penalty / var_review events that aren't already in the log.
    """
    lookback = datetime.utcnow() - timedelta(hours=EVENT_LOOKBACK_HOURS)
    events = (
        db.query(MatchEvent)
        .filter(MatchEvent.match_id == match.id)
        .filter(MatchEvent.captured_at >= lookback)
        .order_by(MatchEvent.elapsed.asc(), MatchEvent.id.asc())
        .all()
    )
    home_name = _team_name(db, match.home_code)
    away_name = _team_name(db, match.away_code)
    lms = db.query(LiveMatchState).filter_by(match_id=match.id).first()

    for ev in events:
        elapsed = ev.elapsed or 0
        extra = ev.extra or 0
        minute = f"{elapsed}{'+' + str(extra) if extra else ''}'"
        player = (ev.player_name or "").strip()
        which_team = ev.team_name or ""

        # --- Goal ---
        if ev.type == "Goal":
            # Shootout kicks arrive as type="Goal" at 120' but are NOT match
            # goals: a decided shootout would burst 8-10 "GOAL 1-1" pushes with
            # a scoreline that never changes. The ShootoutTracker is the
            # shootout UX; pushes stay silent for kicks. (Armed 2026-07-04 when
            # the poller began archiving shootout kicks live.)
            from backend.data.persistence import is_shootout_event
            if is_shootout_event(ev.elapsed, ev.extra, ev.comments):
                continue
            # Missed penalties also ride on type="Goal" — a GOAL push for a
            # miss is wrong. Fire the penalty event bit instead, which is what
            # a user opting into penalty alerts expects.
            if (ev.detail or "") == "Missed Penalty":
                pkey = f"penalty:missed:{match.id}:{elapsed}:{ev.player_id or 'x'}"
                _fire(db, match=match, event_type="penalty", event_key=pkey,
                      event_bit=pe.PENALTY,
                      title=f"Penalty missed · {home_name} v {away_name}",
                      body=f"{player or which_team} misses from the spot at {minute}")
                continue
            # 30s confirm queue mitigates api-football's wrong-player-id
            # reload race (see module docstring).
            if (datetime.utcnow() - ev.captured_at).total_seconds() < GOAL_CONFIRM_DELAY_SECONDS:
                continue
            key = f"goal:{match.id}:{elapsed}:{ev.team_id or 'x'}:{ev.player_id or 'x'}"
            score = _scoreline(match, lms)
            title = f"GOAL {home_name} {score} {away_name}"
            body = f"{player or which_team} · {minute}"
            _fire(db, match=match, event_type="goal", event_key=key,
                  event_bit=pe.GOAL, title=title, body=body)
            # Penalty: if this goal carries detail="Penalty", emit a
            # second penalty event for users who opted into the penalty
            # toggle but not goal (rare but consistent with the FE).
            if (ev.detail or "").lower().startswith("penalty"):
                pkey = f"penalty:scored:{match.id}:{elapsed}:{ev.player_id or 'x'}"
                _fire(db, match=match, event_type="penalty", event_key=pkey,
                      event_bit=pe.PENALTY,
                      title=f"Penalty scored · {home_name} v {away_name}",
                      body=f"{player or which_team} converts at {minute} ({score})")
            continue

        # --- Red card ---
        if ev.type == "Card" and ev.detail in ("Red Card", "Second Yellow card"):
            key = f"red:{match.id}:{elapsed}:{ev.player_id or 'x'}"
            _fire(db, match=match, event_type="red_card", event_key=key,
                  event_bit=pe.RED_CARD,
                  title=f"Red card · {home_name} v {away_name}",
                  body=f"{player or which_team} sent off at {minute}")
            continue

        # --- Penalty missed (Var or Penalty detail without Goal type) ---
        if ev.type == "Var" and "penalty" in (ev.detail or "").lower():
            key = f"penalty:var:{match.id}:{elapsed}:{(ev.detail or '').lower()}"
            _fire(db, match=match, event_type="penalty", event_key=key,
                  event_bit=pe.PENALTY,
                  title=f"Penalty {ev.detail or 'review'} · {home_name} v {away_name}",
                  body=f"{minute} · {ev.comments or ''}".strip())
            continue

        # --- VAR review (non-penalty) ---
        if ev.type == "Var":
            key = f"var:{match.id}:{elapsed}:{(ev.detail or '').lower()}"
            _fire(db, match=match, event_type="var_review", event_key=key,
                  event_bit=pe.VAR_REVIEW,
                  title=f"VAR · {home_name} v {away_name}",
                  body=f"{ev.detail or 'Review'} · {minute}")
            continue


def _dispatch_ht_ft(db, match: Match) -> None:
    """One push at HT, one at FT. Detected by LiveMatchState.status."""
    lms = db.query(LiveMatchState).filter_by(match_id=match.id).first()
    if not lms:
        return
    home_name = _team_name(db, match.home_code)
    away_name = _team_name(db, match.away_code)

    if lms.status == "HT":
        key = f"ht:{match.id}"
        if not _already_fired(db, key):
            score = _scoreline(match, lms)
            _fire(db, match=match, event_type="half_time", event_key=key,
                  event_bit=pe.HALF_TIME,
                  title=f"HT {home_name} {score} {away_name}",
                  body="Half-time")

    if (
        match.status == "complete"
        and match.interruption_status is None  # awarded matches still void picks, no FT push
        and match.home_score is not None
    ):
        key = f"ft:{match.id}"
        if not _already_fired(db, key):
            score = f"{match.home_score}-{match.away_score}"
            _fire(db, match=match, event_type="full_time", event_key=key,
                  event_bit=pe.FULL_TIME,
                  title=f"FT {home_name} {score} {away_name}",
                  body="Full-time")


def _dispatch_kickoff(db, match: Match) -> None:
    """Fires once per match when LiveMatchState first shows a live status."""
    lms = db.query(LiveMatchState).filter_by(match_id=match.id).first()
    if not lms or lms.status not in {"1H", "LIVE"}:
        return
    key = f"kickoff:{match.id}"
    if _already_fired(db, key):
        return
    home_name = _team_name(db, match.home_code)
    away_name = _team_name(db, match.away_code)
    _fire(db, match=match, event_type="kickoff", event_key=key,
          event_bit=pe.KICKOFF,
          title=f"Kickoff · {home_name} v {away_name}",
          body="Underway")


def _dispatch_interruption(db, match: Match) -> None:
    """Suspended / resumed events. Always-on (no toggle, see push_events).
    Detected by Match.interruption_status transitions. The event_key uses
    interruption_started_at to dedup — a re-suspension fires again, a
    repeated check on the same suspension doesn't.
    """
    home_name = _team_name(db, match.home_code)
    away_name = _team_name(db, match.away_code)

    # Suspended — fires while interruption_status is 'delayed' / 'abandoned'.
    if match.interruption_status in ("delayed", "abandoned"):
        started = match.interruption_started_at or datetime.utcnow()
        key = f"suspended:{match.id}:{started.isoformat()[:19]}"
        if not _already_fired(db, key):
            label = "Match abandoned" if match.interruption_status == "abandoned" else "Match suspended"
            reason = (match.interruption_reason or "").split("(")[0].strip() or "Reason TBD"
            _fire(db, match=match, event_type="suspended", event_key=key,
                  event_bit=None,
                  title=f"{label} · {home_name} v {away_name}",
                  body=reason[:140])

    # Resumed — fires when interruption clears AND a prior suspended row
    # exists for this match. NotificationEventLog is the audit trail.
    if match.interruption_status is None:
        prior_suspend = (
            db.query(NotificationEventLog)
            .filter(NotificationEventLog.match_id == match.id)
            .filter(NotificationEventLog.event_type == "suspended")
            .order_by(NotificationEventLog.fired_at.desc())
            .first()
        )
        if prior_suspend is None:
            return
        key = f"resumed:{match.id}:{prior_suspend.id}"
        if not _already_fired(db, key):
            _fire(db, match=match, event_type="resumed", event_key=key,
                  event_bit=None,
                  title=f"Match resumed · {home_name} v {away_name}",
                  body="Play has restarted")


# ---------------------------------------------------------------------------
# Scheduler entry point
# ---------------------------------------------------------------------------


def dispatch_pending_events() -> dict:
    """One scheduler pass. Returns a summary dict the admin dashboard can
    surface so we know the dispatcher is alive.
    """
    summary = {"matches_scanned": 0, "fired": 0}
    db = SessionLocal()
    try:
        # Only look at matches in a state where new events are plausible:
        # currently live (LiveMatchState in 1H/HT/2H/...) OR recently
        # transitioned to complete/abandoned (need to fire FT/suspended).
        # A 12h kickoff window covers ET + cool-down.
        from datetime import datetime as _dt, timedelta as _td
        now = _dt.utcnow()
        recent_lo = now - _td(hours=12)
        recent_hi = now + _td(hours=2)
        matches = (
            db.query(Match)
            .filter(Match.kickoff.isnot(None))
            .filter(Match.kickoff >= recent_lo)
            .filter(Match.kickoff <= recent_hi)
            .all()
        )
        for m in matches:
            summary["matches_scanned"] += 1
            before = summary["fired"]
            _dispatch_kickoff(db, m)
            _dispatch_goals_and_cards_and_var(db, m)
            _dispatch_ht_ft(db, m)
            _dispatch_interruption(db, m)
            after = (
                db.query(NotificationEventLog)
                .filter(NotificationEventLog.match_id == m.id)
                .count()
            )
            # 'fired' is sloppy here — measured as total log rows seen
            # this tick, useful for dashboard hand-wavy "is anything
            # happening". Per-pass fire count is in the logs.
            summary["fired"] = before + after
        return summary
    finally:
        db.close()
