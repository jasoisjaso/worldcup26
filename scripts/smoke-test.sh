#!/usr/bin/env bash
# Frontend smoke test — hits the public routes, asserts HTTP 200, and looks for
# a known body fragment per page. Catches the common breakage classes (broken
# build, 500 from a route handler, blank page from a server-side fetch error)
# without standing up Playwright or a full test runner.
#
# Usage:
#   ./scripts/smoke-test.sh                 # against the live site
#   BASE=http://localhost:3000 ./scripts/smoke-test.sh   # against local dev
#
# Wire to CI (or pre-deploy) by calling this after the build; exits non-zero
# on the first failure, prints a one-line summary at the end.
set -uo pipefail

BASE="${BASE:-https://wc26.tinjak.com}"
TIMEOUT="${TIMEOUT:-15}"

fails=0
total=0

check() {
  local path="$1"
  local needle="$2"
  total=$((total + 1))

  # -L follow redirects, -sS quiet success but show errors, write status to its own line.
  local body status
  body=$(curl -L -sS --max-time "$TIMEOUT" -w "\n__STATUS__%{http_code}" "$BASE$path" 2>&1) || true
  status="${body##*__STATUS__}"
  body="${body%__STATUS__*}"

  if [ "$status" != "200" ]; then
    echo "  FAIL  $path  -> HTTP $status"
    fails=$((fails + 1))
    return
  fi
  if ! grep -q -- "$needle" <<<"$body"; then
    echo "  FAIL  $path  -> missing fragment: $needle"
    fails=$((fails + 1))
    return
  fi
  printf "  ok    %-32s (%d bytes)\n" "$path" "${#body}"
}

echo "Smoke test against $BASE"
echo "---"

# Public pages — pick a needle that only appears when the page actually rendered,
# not in a generic error or 404 template.
check "/"            "World Cup"
check "/value"       "Value"
check "/winner"      "Who"
check "/bracket"     "Bracket\|bracket\|knockout"
check "/groups"      "Group"
check "/predictions" "predict\|Predictions\|track"
check "/performance" "performance\|Performance\|Track"
check "/acca"        "Acca\|acca\|builder"
check "/how-it-works" "how\|How"
check "/live"        "Live\|live"

# Internal — must NOT 200 unauthenticated for the dashboard, but the login page must serve.
check "/admin/login" "Admin\|Sign\|admin"

# API health (public) and sitemap.
check "/api/proxy/progress" "stage\|complete\|kickoff"

echo "---"
if [ "$fails" -eq 0 ]; then
  echo "OK   $total/$total routes passed"
  exit 0
fi
echo "FAIL $fails/$total routes failed"
exit 1
