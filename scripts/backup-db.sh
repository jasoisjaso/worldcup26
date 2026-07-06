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
# Use a busy-timeout so the online backup WAITS for a quiet write window instead
# of failing instantly under contention. The live poller + the harvester (now
# burning ~10 jobs/tick) write every few seconds, so a zero-timeout .backup can
# hit "database is locked" and — under `set -e` in deploy.sh — abort the whole
# deploy. 60s is plenty for any single scheduler write to commit. We also set
# WAL checkpoint mode so the backup reflects the latest committed state.
# The live DB is written by the container as root, so on the VPS the file is
# root-owned. A non-root deploy user then gets "attempt to write a readonly
# database" the instant sqlite3 tries to create the WAL sidecar for the online
# backup — which, under `set -e` in deploy.sh, aborts the whole deploy. Fall
# back to sudo (passwordless on the VPS) when we can't write the DB ourselves.
SQLITE="sqlite3"
if [ ! -w "$DB_PATH" ]; then
  if sudo -n true 2>/dev/null; then
    SQLITE="sudo sqlite3"
  else
    echo "backup-db: WARN $DB_PATH not writable and no passwordless sudo — the online backup may fail" >&2
  fi
fi
$SQLITE "$DB_PATH" \
  ".timeout 300000" \
  ".backup '$dest'"
# $dest may be root-owned if sudo ran the backup; gzip (as the deploy user) can
# still read it (644) and the backups dir is ours, so the replace succeeds.
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
