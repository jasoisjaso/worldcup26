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

### Restore

```bash
docker compose -f docker-compose.prod.yml stop backend
gunzip -c backups/wc2026-YYYY-MM-DD-HHMM.db.gz > data/wc2026.db
docker compose -f docker-compose.prod.yml start backend
curl -s .../health   # confirm status + feed freshness
```

Test a restore at least once so you know it works before you need it.

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
