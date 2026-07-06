#!/usr/bin/env bash
# One-command deploy on the VPS. Backs up the ledger first, fast-forwards main, rebuilds
# the image stamped with the running commit, recreates the containers, and prunes.
# Refuses a non-fast-forward pull so a divergent tree never silently rebuilds.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "==> Backing up the database before anything changes"
# The hourly cron (wc26-hourly.sh) already drops a full gzipped snapshot into
# backups/ every hour, so re-backing-up the ~4GB ledger on every deploy is the
# single biggest deploy cost (minutes of .backup + gzip). Skip it when a fresh
# snapshot (< BACKUP_MAX_AGE_MIN, default 60) already exists. Set FORCE_BACKUP=1
# to always take one (use before a schema migration).
BACKUP_MAX_AGE_MIN="${BACKUP_MAX_AGE_MIN:-60}"
FRESH_BACKUP=""
if [ "${FORCE_BACKUP:-0}" != "1" ]; then
  FRESH_BACKUP="$(find backups -maxdepth 1 -name 'wc2026-*.db.gz' -mmin "-${BACKUP_MAX_AGE_MIN}" 2>/dev/null | head -1)"
fi
if [ -n "$FRESH_BACKUP" ]; then
  age_min=$(( ( $(date +%s) - $(stat -c %Y "$FRESH_BACKUP") ) / 60 ))
  echo "    skip — fresh backup exists (${age_min}m old): $FRESH_BACKUP"
  echo "    (FORCE_BACKUP=1 to back up anyway, e.g. before a migration)"
else
  bash scripts/backup-db.sh
fi

echo "==> Fast-forwarding main"
BEFORE_HEAD="$(git rev-parse HEAD)"
git fetch origin main
git pull --ff-only origin main
AFTER_HEAD="$(git rev-parse HEAD)"

# Only rebuild the service(s) whose code changed. A frontend-only change
# shouldn't pay for a backend rebuild and vice versa. Anything touched OUTSIDE
# frontend/ and backend/ (compose file, root Dockerfiles, scripts) rebuilds
# everything to be safe. FORCE_BUILD_ALL=1 overrides.
CHANGED="$(git diff --name-only "$BEFORE_HEAD" "$AFTER_HEAD" 2>/dev/null || true)"
BUILD_SERVICES=""
if [ "${FORCE_BUILD_ALL:-0}" != "1" ] && [ -n "$CHANGED" ]; then
  fe="$(printf '%s\n' "$CHANGED" | grep -c '^frontend/' || true)"
  be="$(printf '%s\n' "$CHANGED" | grep -c '^backend/' || true)"
  other="$(printf '%s\n' "$CHANGED" | grep -cvE '^(frontend|backend)/' || true)"
  if [ "$other" -eq 0 ]; then
    if [ "$fe" -gt 0 ] && [ "$be" -eq 0 ]; then BUILD_SERVICES="frontend"; fi
    if [ "$be" -gt 0 ] && [ "$fe" -eq 0 ]; then BUILD_SERVICES="backend"; fi
  fi
fi

export GIT_COMMIT="$(git rev-parse --short HEAD)"
if [ -n "$BUILD_SERVICES" ]; then
  echo "==> Building + recreating ONLY [$BUILD_SERVICES] at commit $GIT_COMMIT (other service unchanged)"
else
  echo "==> Building + recreating ALL services at commit $GIT_COMMIT"
fi
# shellcheck disable=SC2086
docker compose -f docker-compose.prod.yml up -d --build $BUILD_SERVICES

echo "==> Pruning dangling images"
docker image prune -f >/dev/null || true

echo "==> Health check (inside the backend container):"
sleep 6
docker exec wc26-backend curl -fsS http://localhost:8000/health || \
  echo "WARN: /health not OK yet — check 'docker compose -f docker-compose.prod.yml logs backend'"
echo
echo "Deployed commit $GIT_COMMIT"
