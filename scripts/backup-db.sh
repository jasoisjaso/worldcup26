#!/usr/bin/env bash
# Online backup of the SQLite prediction ledger — the irreplaceable, by-design
# unreconstructable record behind the public report card (snapshots must be taken
# before kickoff, so a lost DB cannot be rebuilt). sqlite3 .backup is safe on a live
# database; a plain cp can capture a half-written page during a scheduler write.
#
# Run hourly from cron on the VPS. See docs/OPERATIONS.md.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DB_PATH="${DB_PATH:-$SCRIPT_DIR/../data/wc2026.db}"
BACKUP_DIR="${BACKUP_DIR:-$SCRIPT_DIR/../backups}"
RETAIN_HOURS="${RETAIN_HOURS:-168}"   # keep 7 days of rolling backups
RSYNC_TARGET="${RSYNC_TARGET:-}"      # optional off-box dest (user@host:/path or rclone remote)

mkdir -p "$BACKUP_DIR"
if [ ! -f "$DB_PATH" ]; then
  echo "backup-db: database not found at $DB_PATH" >&2
  exit 1
fi

stamp="$(date -u +%F-%H%M)"
dest="$BACKUP_DIR/wc2026-$stamp.db"
sqlite3 "$DB_PATH" ".backup '$dest'"
gzip -f "$dest"
echo "backup-db: wrote $dest.gz"

# Drop anything past the retention window.
find "$BACKUP_DIR" -name 'wc2026-*.db.gz' -mmin "+$((RETAIN_HOURS * 60))" -delete

# Copy off-box if a target is configured (a backup on the same disk is not a backup).
if [ -n "$RSYNC_TARGET" ]; then
  rsync -a "$BACKUP_DIR"/ "$RSYNC_TARGET"/ && echo "backup-db: synced to $RSYNC_TARGET"
fi

# Google Drive off-box backup via rclone. Set GDRIVE_REMOTE to a configured
# rclone remote path like "gdrive:wc26-backups" (the remote itself is set up
# once with `rclone config`; see docs/OPERATIONS.md). Only the most recent
# backup is uploaded each tick — rclone diff-syncs the rest of the rolling
# 7-day window so we don't re-upload unchanged files. Idempotent + safe to
# run repeatedly; failures don't break the local backup.
GDRIVE_REMOTE="${GDRIVE_REMOTE:-}"
if [ -n "$GDRIVE_REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  if rclone sync "$BACKUP_DIR"/ "$GDRIVE_REMOTE"/ \
      --include 'wc2026-*.db.gz' \
      --transfers 2 --checkers 4 --quiet; then
    echo "backup-db: synced to Google Drive ($GDRIVE_REMOTE)"
  else
    echo "backup-db: WARN rclone sync to $GDRIVE_REMOTE failed (local backup still saved)" >&2
  fi
fi
