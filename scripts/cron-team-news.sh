#!/usr/bin/env bash
# Daily harvest of per-team news + community pulse.
#
# Runs from cron on the VPS at 6am UTC. Pulls the repo, refits the
# team-news.json snapshot via the last30days engine, and — only when the
# JSON actually changed — commits, pushes, and triggers a fresh deploy.
#
# Idempotent: wrap in flock so overlapping runs can't fight.
#
# Log: /home/ubuntu/wc26-team-news-cron.log

set -uo pipefail

REPO=/home/ubuntu/worldcup26
ENGINE=/home/ubuntu/.claude/skills/last30days/scripts/last30days.py
PY=/usr/bin/python3.12
JSON=frontend/public/data/team-news.json

log() { echo "[$(date -Iseconds)] $*"; }

log "=== team-news cron START ==="

if [ ! -d "$REPO" ]; then
  log "repo missing at $REPO; abort"
  exit 1
fi

cd "$REPO"

# 1. Sync with Gitea first so we don't fight a concurrent manual deploy.
log "pulling latest from origin"
if ! git pull --ff-only origin main 2>&1 | sed 's/^/  /'; then
  log "git pull failed; abort (manual intervention)"
  exit 2
fi

# 2. Run the harvester. Full refresh of all 48 teams. Worst case ~60min wall.
log "running harvester (timeout=600 workers=3)"
if ! "$PY" scripts/harvest_team_news.py --timeout 600 --workers 3; then
  log "harvester exited non-zero; continue anyway and see if any JSON delta was written"
fi

# 3. Did the JSON actually change?
if git diff --quiet -- "$JSON"; then
  log "no change to $JSON — skipping commit + deploy"
  log "=== team-news cron DONE (no-op) ==="
  exit 0
fi

# 4. Commit + push the new snapshot.
log "JSON changed; committing"
STAMP=$(date -u +%Y-%m-%d)
git add "$JSON"
git -c user.name="wc26-cron" -c user.email="cron@wc2026" \
  commit -m "team-news: daily auto-refresh ${STAMP}" -m "Auto-harvest via scripts/cron-team-news.sh"
if ! git push origin main 2>&1 | sed 's/^/  /'; then
  log "git push to gitea failed; abort before deploy"
  exit 3
fi

# 5. Redeploy the frontend so the new JSON is served.
log "running deploy.sh"
bash scripts/deploy.sh 2>&1 | sed 's/^/  /'

log "=== team-news cron DONE (deployed) ==="
