"""Event-type taxonomy + bitmask for per-match / per-team follow alerts.

Each followed row carries an `event_mask` integer where bit N = 1 means
"deliver event type N to this subscriber". The bit layout is part of
the FE contract — see frontend/lib/types.ts FollowEvent enum.

Two events are deliberately NOT in the mask:
  * `suspended` — always fires for any followed match (the FRA-IRQ class
    of bug; users MUST know if play was paused).
  * `resumed` — same logic in reverse.

These are dispatched unconditionally and have no toggle. Everything
else in the table below is opt-in / opt-out.
"""
from __future__ import annotations

# Bit positions. Wire-stable — DO NOT renumber or the FE's saved masks
# become wrong overnight. New event types append at the next free bit.
KICKOFF          = 1 << 0   #   1
GOAL             = 1 << 1   #   2
RED_CARD         = 1 << 2   #   4
HALF_TIME        = 1 << 3   #   8
FULL_TIME        = 1 << 4   #  16
LINEUP_PUBLISHED = 1 << 5   #  32
VAR_REVIEW       = 1 << 6   #  64
PENALTY          = 1 << 7   # 128

# Human label per bit — used by the FE toggle drawer and the admin
# event log so we don't litter the FE with hard-coded strings.
LABELS: dict[int, str] = {
    KICKOFF:          "Kickoff",
    GOAL:             "Goal",
    RED_CARD:         "Red card",
    HALF_TIME:        "Half-time score",
    FULL_TIME:        "Full-time score",
    LINEUP_PUBLISHED: "Lineup published",
    VAR_REVIEW:       "VAR review",
    PENALTY:          "Penalty awarded / missed",
}

# Default-on set when a user first taps Follow.
# Lineup is OFF (60min pre-KO is in-app territory; pushed lineup feels noisy).
# Everything else is ON — VAR and penalty included per user decision
# 2026-06-23 (override of the FotMob default-off pattern).
DEFAULT_MASK: int = (
    KICKOFF | GOAL | RED_CARD | HALF_TIME | FULL_TIME | VAR_REVIEW | PENALTY
)
# Computed: 1 + 2 + 4 + 8 + 16 + 64 + 128 = 223


# Always-on events that bypass event_mask entirely. These do NOT appear
# in the FE toggle UI because users shouldn't be able to silence them.
ALWAYS_ON_EVENTS = frozenset({"suspended", "resumed"})


def mask_enabled(mask: int, event_bit: int) -> bool:
    """True if `event_bit` is set in `mask`."""
    return bool(mask & event_bit)


def event_type_to_bit(event_type: str) -> int | None:
    """Reverse-lookup: dispatcher gets an event_type string from the live
    poller ('goal', 'red_card', etc.) and needs the bit to check against
    each followed subscriber's mask. Returns None for unknown types
    (caller will then check ALWAYS_ON_EVENTS).
    """
    return {
        "kickoff":          KICKOFF,
        "goal":             GOAL,
        "red_card":         RED_CARD,
        "half_time":        HALF_TIME,
        "full_time":        FULL_TIME,
        "lineup_published": LINEUP_PUBLISHED,
        "var_review":       VAR_REVIEW,
        "penalty":          PENALTY,
    }.get(event_type)
