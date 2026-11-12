# Running MailForge on a NAS

Written for Synology DSM 7.2+ (Container Manager); QNAP Container Station, Unraid and TrueNAS differ only in where the UI lives.

## Requirements
- Docker with Compose (Synology: *Container Manager*), SSH access, and an **x86-64 CPU**. The published image is amd64-only; on an ARM NAS build locally (`docker compose build`).
- An Anthropic API key and at least one mail account's credentials (see README → Credentials).

## 1. Get the files onto the NAS
Over SSH (enable it in DSM → Control Panel → Terminal & SNMP):

```bash
mkdir -p /volume1/docker/mailforge && cd /volume1/docker/mailforge
git clone https://github.com/reza-t/mailforge.git .      # or download the ZIP from GitHub and extract it here
mkdir -p data reports
cp .env.example .env
cp config/accounts.example.yaml config/accounts.yaml
```

## 2. Configure
Edit `.env` and `config/accounts.yaml` (File Station, `vi`, or your editor of choice).

- `MAILFORGE_UID` / `MAILFORGE_GID`: run `id <your-nas-user>` and copy the numbers (Synology users are usually 1026+, not 1000).
- Make `data` and `reports` writable by that user: `sudo chown -R <uid>:<gid> data reports`.
- `TZ`: your timezone (e.g. `Europe/Berlin`), otherwise the 07:30 schedule runs in UTC.
- Gmail/Outlook refresh tokens need a browser. Create them on your PC with `scripts/get_oauth_token.py`, then paste them into `.env`. Yahoo only needs an app password.
- `chmod 600 .env`: it holds your API key.

## 3. Start
```bash
cd /volume1/docker/mailforge
sudo docker compose pull                     # sudo docker compose build  <- on ARM or if the GHCR package is private
sudo docker compose run --rm mailforge-worker python -m mailforge.main --dry-run   # fetch + filter, no API calls
sudo docker compose run --rm mailforge-worker python -m mailforge.main --force     # real run, emails the report
sudo docker compose up -d                    # daily at 07:30
```
Container Manager UI alternative: *Project → Create*, path `/volume1/docker/mailforge`, use the existing `docker-compose.yml`.

Reports appear in `/volume1/docker/mailforge/reports/`; logs: `sudo docker compose logs -f ofelia mailforge-worker`.

## 4. Optional: no Docker socket (more secure)
Ofelia needs `/var/run/docker.sock`. To avoid that, delete the `ofelia` service from `docker-compose.yml` and use DSM
*Control Panel → Task Scheduler → Create → Scheduled Task → User-defined script* (run as `root`, daily 07:30):

```bash
docker exec mailforge-worker python -m mailforge.main
```

## Updating
```bash
cd /volume1/docker/mailforge && git pull && sudo docker compose pull && sudo docker compose up -d
```

## Troubleshooting
| Symptom | Fix |
|---|---|
| `permission denied` on `/app/data` | `chown` data/reports to `MAILFORGE_UID:GID` |
| `pull access denied` / `unauthorized` | Make the GHCR package public, or use `docker compose build` |
| `exec format error` | ARM NAS: use `docker compose build` |
| Job never fires | Check `TZ`; `docker compose logs ofelia` should list `mailforge-daily` |
| No email, report saved | See worker log: SMTP/app-password problem; the `.md` is still in `reports/` |
