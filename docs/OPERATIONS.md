# Operations

How the live site at [wc26.tinjak.com](https://wc26.tinjak.com) is deployed, backed up, and monitored. Everything here runs on the VPS from the repo checkout.

## Deploy

```bash
cd /path/to/worldcup26
./scripts/deploy.sh
```

The script backs up the database first, fast-forwards `main` (refusing a divergent pull), rebuilds the backend image stamped with the current commit, recreates both containers, and prunes dangling images. The running commit is then visible at `/health` under `commit`.

Never run a manual `docker compose ... up --build` without backing up first. Use the script.

## Database backups

`data/wc2026.db` is the only copy of every pre-kickoff prediction snapshot, settled pick, closing line, and CLV value. It is gitignored and bind-mounted into the backend container. Because snapshots are taken before kickoff, a lost database **cannot be reconstructed**, so it is backed up hourly.

```bash
./scripts/backup-db.sh
```

This uses SQLite's online `.backup` (safe on a live database, unlike `cp`), gzips the result into `backups/`, keeps 7 days rolling, and rsyncs off-box when `RSYNC_TARGET` is set.

Install the hourly cron once:

```bash
crontab -e
# add (adjust the path):
0 * * * * RSYNC_TARGET=user@backup-host:/srv/wc2026-backups /path/to/worldcup26/scripts/backup-db.sh >> /var/log/wc2026-backup.log 2>&1
```

A backup on the same disk is not a backup. Set `RSYNC_TARGET` to an off-box destination.

### Google Drive backup (free, easy)

For an off-box destination without spinning up another server, we sync the rolling backup directory to Google Drive via rclone:

1. On the VPS, install rclone (one-time):
   ```bash
   curl -sSL https://rclone.org/install.sh | sudo bash
   ```
2. Configure a `gdrive` remote:
   ```bash
   rclone config
   # answer: n (new remote)  →  name: gdrive  →  storage: drive (Google Drive)
   # client_id: leave blank   →  client_secret: leave blank
   # scope: 1 (full access)   →  service_account_file: leave blank
   # Edit advanced config: n  →  Use auto config: n (we're headless)
   ```
3. rclone prints a URL — open it on a machine with a browser, sign in to the Google account you want backups in, copy the auth code, paste it back in the SSH session, accept the team-drive prompt, save the config.
4. Set the cron to pass `GDRIVE_REMOTE` to the backup script:
   ```bash
   0 * * * * GDRIVE_REMOTE=gdrive:wc26-backups /home/ubuntu/worldcup26/scripts/backup-db.sh >> /home/ubuntu/wc2026-backup.log 2>&1
   ```
5. Test it once: `GDRIVE_REMOTE=gdrive:wc26-backups bash scripts/backup-db.sh`. The first run creates the `wc26-backups` folder in your Drive and uploads every existing `.db.gz` (rclone diff-syncs after that).

The backup script keeps a 7-day rolling local window plus everything in Drive (rclone diff-sync mirrors the local pruning). Failures in the Drive sync are logged but never block the local backup.

### Restore

```bash
docker compose -f docker-compose.prod.yml stop backend
gunzip -c backups/wc2026-YYYY-MM-DD-HHMM.db.gz > data/wc2026.db
docker compose -f docker-compose.prod.yml start backend
curl -s .../health   # confirm status + feed freshness
```

Test a restore at least once so you know it works before you need it.

## Harvest queue priority overrides

The harvester pulls jobs by ascending priority (lower = sooner). All per-fixture fan-out jobs default to **priority 250**. The startup seeder enqueues EPL + Bundesliga fixtures for seasons 2023 and 2024.

To narrow the active harvest window without losing data — e.g. "focus on current season first" — use `scripts/demote_2023.py` (the `scripts/` dir isn't baked into the image, so we copy it in first):

```bash
cd /home/ubuntu/worldcup26
docker cp scripts/demote_2023.py wc26-backend:/tmp/demote_2023.py

# Dry-run (always do this first)
docker exec wc26-backend bash -c "cd /app && PYTHONPATH=/app python3 /tmp/demote_2023.py"

# Apply: bumps all pending 2023-season fan-out jobs to priority 900
docker exec wc26-backend bash -c "cd /app && PYTHONPATH=/app python3 /tmp/demote_2023.py --apply"

# Revert: put them back at priority 250 (next in line again)
docker exec wc26-backend bash -c "cd /app && PYTHONPATH=/app python3 /tmp/demote_2023.py --apply --revert"
```

What the script does:
- Reads the 4 already-completed `/fixtures` responses to learn which fixture IDs belong to season 2023
- Looks up every `pending` row whose `params_json.fixture` is in that set
- Updates only the `priority` column — zero deletions, zero API calls, fully reversible
- Logs the count it changed and a per-endpoint breakdown

Deferred rows still have their dedup keys, so the startup seeder can't re-add them. Revert is the only way they come back.

**Active at the time of writing (2026-06-21):** EPL + Bundesliga 2023 fan-out jobs are demoted to priority 900. The harvester is working through 2024 season only, ETA ~2 weeks to 100%.

## Admin dashboard (`/admin`)

Internal-only operator UI for the api-football harvester. Hidden from the public nav, excluded from `robots.txt`/`sitemap.xml`, and gated by a server-side bearer token.

### Setup (one-time)

1. Pick a long random token (e.g. `openssl rand -hex 32`).
2. Add it to `backend/.env` on the VPS:
   ```
   WC26_ADMIN_TOKEN=<the-long-random-string>
   ```
3. Restart the backend so the env is picked up:
   ```bash
   docker compose -f docker-compose.prod.yml up -d --force-recreate backend
   ```
4. Browse to `https://wc26.tinjak.com/admin/login`, paste the token. A 12h `HttpOnly` cookie is minted so you don't paste it again on the same device.

Rotating `WC26_ADMIN_TOKEN` invalidates every minted cookie immediately (the server-side proxy re-presents the cookie value to the backend on each call).

### What the dashboard shows
- **Quota gauge** — api-football remaining / 7,500, burn rate, projected daily total, exhaust risk
- **Phase indicator** — backfill / harvest / burn (the three time windows the consumers gate on)
- **Feed health** — every scheduler job, last-success age, stale highlight
- **Queue** — pending / in-progress / done / error counts, last completed, last error
- **Raw blobs + normalised tables** — archive size, processed ratio
- **On-disk caches** — odds, tournament, quota state files; sizes + ages
- **Recent errors** — last 5 harvest errors with timestamp + endpoint
- **Manual actions** — pause/resume, run one tick, seed buttons (WC squads / leagues / full stack)

The page refreshes every 30 s.

### Pause/resume
Pause is the operator's "stop burning quota now" button. It writes a `settings_kv` row (`harvest_paused=1`) which every api-football consumer gate (`harvester`, `auto_backfill`, `injuries_persist`) reads before each tick. Survives container restart. Live polling (scores/events) is intentionally **not** affected — the UI still shows live matches while the harvester is paused.

## Monitoring

`GET /health` returns liveness plus data-feed freshness:

```json
{
  "status": "ok",            // "degraded" if any feed is stale
  "commit": "a505edc",       // exactly what is deployed
  "odds_quota_remaining": 480,
  "all_fresh": true,
  "degraded": [],
  "feeds": {
    "score_refresh": { "label": "Match results", "age_minutes": 4.2, "stale": false, ... }
  }
}
```

A feed is `stale` once it is more than 3x past its own refresh interval, so a single skipped run does not trip it. Point an uptime check at `/health` and alert when the body has `status: "degraded"` or any feed `stale: true`. `odds_quota_remaining` warns in the logs once it drops to the floor (25), before the value board and CLV capture go dark.

### Known degraded feeds

API-Football access is currently unavailable, so the injuries, lineups, club-xG and squad-value signals run in a reduced/static mode. This is expected, not a regression. The remaining model (Dixon-Coles + confederation-aware ELO + the other context modifiers) is unaffected.
