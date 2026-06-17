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
