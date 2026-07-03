/**
 * Shared event predicates. Mirrors backend/data/persistence.py's
 * is_shootout_event so FE components and backend jobs agree on what counts
 * as a shootout kick: api-football stamps them comments="Penalty Shootout"
 * at elapsed=120 (older payloads only mark them by a minute past 120).
 *
 * Shootout kicks ride on type="Goal" like real goals, so every goal-shaped
 * list (recap timeline, live ticker, scorer tallies) must exclude them —
 * only the ShootoutTracker renders them, as kicks.
 */
export function isShootoutKick(e: {
  elapsed?: number | null
  extra?: number | null
  comments?: string | null
}): boolean {
  if ((e.comments || "").toLowerCase().includes("shootout")) return true
  return ((e.elapsed || 0) + (e.extra || 0)) > 120
}
