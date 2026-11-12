# Running MailForge on a NAS

Written for Synology DSM 7.2+ (Container Manager); [UGREEN UGOS notes below](#ugreen-ugos-pro). QNAP, Unraid and TrueNAS differ only in where the UI lives.

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

## Running it with Portainer

Use `docker-compose.portainer.yml` (no build step, absolute paths, variables from Portainer instead of a `.env` file).

1. **Create the folders on the NAS** (File Station or SSH): `/volume1/docker/mailforge/{config,data,reports}` (adjust the path for your NAS, e.g. a UGREEN shared folder).
   Set ownership of `data` and `reports` to the UID/GID you will use (`id <user>`), and put your edited `accounts.yaml` (from `config/accounts.example.yaml`) into `config/`. Secrets stay out of it; it only names env vars.
2. **Portainer → Stacks → Add stack**, name `mailforge`.
   - *Build method* **Repository**: URL `https://github.com/reza-t/mailforge`, reference `refs/heads/main`, compose path `docker-compose.portainer.yml`.
     (Or choose **Web editor** and paste the contents of that file.)
3. **Environment variables → Advanced mode**, paste the contents of your filled-in `.env` (see `.env.example`): `ANTHROPIC_API_KEY`, `TZ`, `MAILFORGE_UID`, `MAILFORGE_GID`, delivery settings, and each account's credentials.
   Add `MAILFORGE_DIR=/volume1/docker/mailforge` if your folder is elsewhere.
4. **Deploy the stack.** If the image pull is denied, make the GHCR package public or add ghcr.io under Portainer → Registries.
5. **Test:** Containers → `mailforge-worker` → **Console** → *Connect* with command `/bin/sh`, then:
   ```
   python -m mailforge.main --dry-run     # fetch + filter only
   python -m mailforge.main --force       # real run, emails the report
   ```
   Check `reports/` on the NAS and your inbox. After that the Ofelia container runs it daily at 07:30 (`TZ`). Ofelia logs: Containers → `ofelia` → Logs.
6. **Update:** Stacks → `mailforge` → **Pull and redeploy** (re-pulls the image).

Notes: Portainer stores the variables (including your API key) in its own database, so protect the Portainer login. Changing `accounts.yaml` needs no redeploy; restart the `mailforge-worker` container only if you change variables.

## UGREEN (UGOS / UGOS Pro)

UGREEN NAS models (DXP/DH/iDX series) are x86-64, so the prebuilt GHCR image works. The steps match the Synology ones above, with these differences:

1. **Enable SSH:** Control Panel → Terminal → enable SSH, then `ssh <admin-user>@<nas-ip>`.
2. **Install Docker:** App Center → install **Docker**. (Compose needs a recent UGOS; check with `docker compose version`. If it is missing, update UGOS first.)
3. **Pick a location on a storage pool**, not the system disk, e.g. a shared folder you created in Files:
   ```bash
   cd /volume1/<your-shared-folder> && mkdir -p mailforge && cd mailforge   # adjust to your pool/volume path
   git clone https://github.com/reza-t/mailforge.git . && mkdir -p data reports
   ```
   If `git` is not installed, download the ZIP from GitHub and upload it with Files.
4. **UID/GID and permissions:** run `id` for your user (usually 1000+ and a group such as 10); set `MAILFORGE_UID`/`MAILFORGE_GID` to those and `sudo chown -R <uid>:<gid> data reports`. Set `TZ`, `chmod 600 .env`.
5. **Run:** use the same `sudo docker compose pull / --dry-run / --force / up -d` commands as above.
   In the Docker app you can instead use **Project → Create** and point it at the folder containing `docker-compose.yml`.
6. **No Ofelia?** UGOS has no documented cron UI that I can vouch for; use `crontab -e` over SSH, or keep Ofelia (it only needs `/var/run/docker.sock`, which the Docker app provides):
   ```
   30 7 * * * docker exec mailforge-worker python -m mailforge.main
   ```

> I wrote the UGOS menu names from general knowledge and have not tested them on a UGREEN device; menu labels vary by UGOS version. The Docker commands themselves are standard.
