"""Central rules for whether a pick / multi should settle, void, or wait.

Every settlement site (single picks in history.py, multis in multi_picker.py,
future per-market settlers) routes through here so the void semantics stay
consistent — there's no second voice on "did this match really finish".

Industry alignment (researched 2026-06-23, sources in
docs/plans/2026-06-23_match-interruption-handling.md §7b):
  * bet365 / Betfair / Sky Bet / Paddy Power converge on: void if abandoned
    before 90' unless the outcome was already determined at the moment of
    abandonment.
  * Resumed-and-finished within local-midnight: bets stand normally.
  * Authority-awarded results (3-0 walkover) still void per bet365 + the
    Serbia-Albania drone precedent.

Our model: Match.interruption_status carries the *why*. A match with
non-NULL interruption_status is voided for picks irrespective of its
Match.status (awarded matches DO update standings but picks still void).
That's the conservative bookmaker default and the right MVP — a
per-market "outcome already determined" refinement (e.g. over 0.5 goals
after a goal was scored) can land later if real money rides on it.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.db.models import Match


# Any of these on Match.interruption_status voids picks/multis.
# 'delayed' is included because the match hasn't actually finished yet —
# picks must NOT settle on a partial score even if the match later resumes
# (we'll re-evaluate against the real FT once Match.interruption_status
# goes back to NULL via the live poller / watchdog).
_VOID_STATUSES = {"delayed", "postponed", "abandoned", "awarded"}


def pick_voided(match: "Match | None") -> bool:
    """True if a pick on this match should be voided (stake refunded).

    Returns False for a non-existent match (caller decides what to do —
    history pages render 'pending', multi settler waits another pass).
    """
    if match is None:
        return False
    return (match.interruption_status or None) in _VOID_STATUSES


def pick_settle_able(match: "Match | None") -> bool:
    """True if a pick on this match should be graded now.

    Requires Match.status == 'complete' AND interruption_status NULL.
    An 'awarded' match is settle-able for STANDINGS but not for PICKS —
    per industry rule that one stays void. Settlement sites must call
    pick_voided() first; if False, then check this for the win/loss grade.
    """
    if match is None:
        return False
    if (match.interruption_status or None) in _VOID_STATUSES:
        return False
    if match.status != "complete":
        return False
    return match.home_score is not None and match.away_score is not None
