/**
 * Round labels for the WC2026 bracket.
 *
 *   matchday 1-3 → Group Stage
 *   matchday 4   → Round of 32
 *   matchday 5   → Round of 16
 *   matchday 6   → Quarter-finals
 *   matchday 7   → Semi-finals
 *   matchday 8   → Final
 *
 * Knockouts have `group=null`; the matchday number is the only signal.
 */

export type RoundKey = "group" | "r32" | "r16" | "qf" | "sf" | "final"

export interface Round {
  key: RoundKey
  label: string
  shortLabel: string
  matchdays: number[]
}

export const ROUNDS: Round[] = [
  { key: "group", label: "Group Stage",     shortLabel: "Group",   matchdays: [1, 2, 3] },
  { key: "r32",   label: "Round of 32",     shortLabel: "R32",     matchdays: [4] },
  { key: "r16",   label: "Round of 16",     shortLabel: "R16",     matchdays: [5] },
  { key: "qf",    label: "Quarter-finals",  shortLabel: "QF",      matchdays: [6] },
  { key: "sf",    label: "Semi-finals",     shortLabel: "SF",      matchdays: [7] },
  { key: "final", label: "Final",           shortLabel: "Final",   matchdays: [8] },
]

export const ROUND_BY_KEY: Record<RoundKey, Round> = ROUNDS.reduce((acc, r) => {
  acc[r.key] = r
  return acc
}, {} as Record<RoundKey, Round>)

export function roundForMatchday(matchday: number): Round {
  for (const r of ROUNDS) {
    if (r.matchdays.includes(matchday)) return r
  }
  return ROUNDS[0]
}

export function roundLabel(matchday: number): string {
  return roundForMatchday(matchday).label
}

export function isKnockout(matchday: number): boolean {
  return matchday >= 4
}
