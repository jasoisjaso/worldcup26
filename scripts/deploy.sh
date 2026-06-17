#!/usr/bin/env bash
# One-command deploy on the VPS. Backs up the ledger first, fast-forwards main, rebuilds
# the image stamped with the running commit, recreates the containers, and prunes.
# Refuses a non-fast-forward pull so a divergent tree never silently rebuilds.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

echo "==> Backing up the database before anything changes"
bash scripts/backup-db.sh

echo "==> Fast-forwarding main"
git fetch origin main
git pull --ff-only origin main

export GIT_COMMIT="$(git rev-parse --short HEAD)"
echo "==> Building + recreating at commit $GIT_COMMIT"
docker compose -f docker-compose.prod.yml up -d --build

echo "==> Pruning dangling images"
docker image prune -f >/dev/null || true

echo "==> Health check (inside the backend container):"
sleep 6
docker exec wc26-backend curl -fsS http://localhost:8000/health || \
  echo "WARN: /health not OK yet — check 'docker compose -f docker-compose.prod.yml logs backend'"
echo
echo "Deployed commit $GIT_COMMIT"
