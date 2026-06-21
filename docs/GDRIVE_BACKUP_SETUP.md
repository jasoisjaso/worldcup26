# Google Drive backup — when you're ready

Pre-staged for you: rclone is installed on the VPS and `scripts/backup-db.sh` already
reads `GDRIVE_REMOTE`. You do this once, in front of a browser, and it's done forever.

## SSH onto the VPS

```bash
sshpass -p 'Jaso1234$' ssh -o PreferredAuthentications=password -o PubkeyAuthentication=no ubuntu@51.161.134.191
```

## Run rclone config (one-time)

```bash
rclone config
```

Answer the prompts in this exact order:

1. `n` (new remote)
2. name: `gdrive`
3. storage: `drive` (Google Drive)
4. client_id: press Enter (blank)
5. client_secret: press Enter (blank)
6. scope: `1` (full access)
7. service_account_file: press Enter
8. Edit advanced config: `n`
9. Use auto config: `n` (we're headless)

rclone will print a URL.

## The browser dance

Copy the URL → open in any browser → sign into the Google account where you want
backups → Google shows an auth code → paste the code back into the SSH session.

Then answer:

- Configure as team drive: `n` (unless you want a shared drive)
- Save: `y`
- Quit: `q`

## Test it once

```bash
GDRIVE_REMOTE=gdrive:wc26-backups bash /home/ubuntu/worldcup26/scripts/backup-db.sh
```

If the last line says "synced to Google Drive", check your Google Drive — there's
a new `wc26-backups` folder with every `wc2026-*.db.gz` from the rolling 7-day window.

## Make it permanent (cron)

```bash
crontab -e
```

Replace the existing `:00` hourly backup line with:

```cron
0 * * * * GDRIVE_REMOTE=gdrive:wc26-backups cd /home/ubuntu/worldcup26 && bash scripts/backup-db.sh >> /home/ubuntu/wc2026-backup.log 2>&1
```

Done. Off-box hourly backup, ~1.2MB per file, well inside the free 15GB Drive quota.

## "Can we do this from /admin instead?"

Technically yes, realistically not worth it:
1. Register OAuth client_id/secret in Google Cloud Console
2. Add an OAuth callback route to our Next.js app
3. Store the refresh token server-side
4. Re-run `rclone config create` with the token blob

That's ~3-4 h of careful, reversible work. The CLI flow above is 60 s.
Say the word if you want the dashboard lane built — I'll spec it.
