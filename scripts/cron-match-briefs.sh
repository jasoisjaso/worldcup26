#!/usr/bin/env bash
# Per-match community brief harvest, run every 6 hours on the VPS.
#
# Triggered by crontab `0 */6 * * *`. Pulls the repo, runs the match-brief
# harvester against the next 36 hours of upcoming matches, and — only when
# the JSON actually changed — commits, pushes, and triggers a fresh deploy.
#
# Idempotent: crontab wraps in flock so overlapping runs can't fight.
#
# Log: /home/ubuntu/wc26-match-briefs-cron.log

set -uo pipefail

REPO=/home/ubuntu/worldcup26
ENGINE=/home/ubuntu/.claude/skills/last30days/scripts/last30days.py
PY=/usr/bin/python3.12
JSON=frontend/public/data/match-briefs.json

log() { echo "[$(date -Iseconds)] $*"; }

log "=== match-briefs cron START ==="

if [ ! -d "$REPO" ]; then
  log "repo missing at $REPO; abort"
  exit 1
fi

cd "$REPO"

# 1. Sync with Gitea before harvesting.
log "pulling latest from origin"
if ! git pull --ff-only origin main 2>&1 | sed 's/^/  /'; then
  log "git pull failed; abort (manual intervention)"
  exit 2
fi

# 2. Run the harvester. Look-ahead 36h covers a full daily cycle plus buffer.
log "running match-brief harvester (hours=36 timeout=600 workers=3)"
if ! "$PY" scripts/harvest_match_briefs.py --hours 36 --timeout 600 --workers 3; then
  log "harvester exited non-zero; continue and check for any JSON delta"
fi

# 3. Did the JSON actually change?
if git diff --quiet -- "$JSON"; then
  log "no change to $JSON — skipping commit + deploy"
  log "=== match-briefs cron DONE (no-op) ==="
  exit 0
fi

# 4. Commit + push the new snapshot.
log "JSON changed; committing"
STAMP=$(date -u +%Y-%m-%dT%H:%MZ)
git add "$JSON"
git -c user.name="wc26-cron" -c user.email="cron@wc2026" \
  commit -m "match-briefs: auto-refresh ${STAMP}" -m "Auto-harvest via scripts/cron-match-briefs.sh"
if ! git push origin main 2>&1 | sed 's/^/  /'; then
  log "git push to gitea failed; abort before deploy"
  exit 3
fi

# 5. Redeploy the frontend so the new JSON is served.
log "running deploy.sh"
bash scripts/deploy.sh 2>&1 | sed 's/^/  /'

log "=== match-briefs cron DONE (deployed) ==="
