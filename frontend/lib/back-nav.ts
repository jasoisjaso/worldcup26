/**
 * Back-navigation safety: allow only known in-app paths as the `?from=` target,
 * so an attacker can't craft `/match/M001?from=https://evil.example/phish` and
 * make our chevron-back into an open redirect.
 *
 * Two acceptance tests:
 *   1. Path is in a static allow-set (homepage and the eight section pages), OR
 *   2. Path matches the safe team-profile shape /team/<lowercase-code>.
 * Anything else falls back to the canonical parent.
 */

const ALLOWED_PARENTS = new Set([
  "/",
  "/value",
  "/acca",
  "/bracket",
  "/groups",
  "/scenarios",
  "/winner",
  "/predictions",
  "/performance",
  "/match3",
])

const TEAM_PATH = /^\/team\/[a-z]{2}(?:-[a-z]{3})?$/ // /team/fr, /team/gb-eng

const FROM_LABELS: Record<string, string> = {
  "/": "All matches",
  "/value": "Value board",
  "/acca": "Acca builder",
  "/bracket": "Bracket",
  "/groups": "Group tables",
  "/scenarios": "Scenarios",
  "/winner": "World Cup odds",
  "/predictions": "My picks",
  "/performance": "Report card",
  "/match3": "Match 3 watch",
}

export interface BackTarget {
  href: string
  label: string
}

/**
 * Resolve a `from` query value into a safe (href, label) pair.
 * `fallback` is the canonical parent for the current page (e.g. `/` for /match/<id>).
 */
export function resolveBack(from: string | undefined, fallback: BackTarget): BackTarget {
  if (!from || typeof from !== "string") return fallback

  if (ALLOWED_PARENTS.has(from)) {
    return { href: from, label: FROM_LABELS[from] ?? fallback.label }
  }
  if (TEAM_PATH.test(from)) {
    return { href: from, label: "Team" }
  }
  return fallback
}
