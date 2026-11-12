# MailForge

Self-hosted, Docker Compose–based daily email briefing. MailForge pulls unread mail from multiple
**Gmail**, **Outlook / Microsoft 365** and **Yahoo** accounts, removes noise deterministically in Python,
asks **Claude** to summarize only what's left (with strict token budgeting), saves a Markdown briefing and
emails it to you.

## Architecture

```
accounts ─► fetch (isolated per provider) ─► deterministic filter ─► dedup (SQLite) ─► clean/truncate
                                                                                         │
 inbox ◄─ email (SMTP / Gmail API / Graph) ◄─ reports/YYYY-MM-DD-digest.md ◄─ Sonnet synthesis ◄─ Haiku triage
```

| Step | What happens | Tokens |
|---|---|---|
| Filter | Own-report loop guard, `List-Unsubscribe` / `Precedence: bulk` / `Auto-Submitted`, `ignore_senders` (VIP domains exempt from header rules) | 0 |
| Dedup | `data/state.db` tracks `(account_id, message_id, thread_id, content_hash, processed_at)`; same content across accounts is sent once | 0 |
| Hygiene | Prefer `text/plain`; HTML stripped (`style/script/head/img`); quoted replies removed; bodies cut at 3,500 chars | 0 |
| Stage 1 | Haiku triage, ≤15 emails/request, JSON `cat/urg/summary/action_item/due_date`; `SKIP` dropped | low |
| Stage 2 | Sonnet writes the briefing from surviving JSON only (skipped when nothing survives) | low |

Provider/LLM/delivery failures never crash the run: they appear in a **System Alerts** banner in the report,
and unprocessed mail is retried next run. The report is always written to disk before delivery.

## Quickstart

```bash
git clone https://github.com/<you>/mailforge.git && cd mailforge
cp .env.example .env && cp config/accounts.example.yaml config/accounts.yaml
# edit both; set MAILFORGE_UID/GID to `id -u` / `id -g`
docker compose pull        # prebuilt image from GHCR (or `docker compose build` to build locally)
docker compose run --rm mailforge-worker python -m mailforge.main --dry-run   # fetch + filter only, no LLM
docker compose run --rm mailforge-worker python -m mailforge.main --force     # real run now
docker compose up -d                                                           # daily at 07:30 (TZ from .env)
```

Add, remove or disable (`enabled: false`) accounts purely in `config/accounts.yaml` + `.env` — no code changes.
CLI flags: `--dry-run` (no LLM, no state writes, no delivery), `--force` (ignore dedup + daily budget).

> The `Publish image` workflow pushes `ghcr.io/<owner>/mailforge-worker` on every push to `main`. After the first run, set the package visibility to *Public* in GitHub (Packages) so `docker compose pull` works without login. Forks: set `MAILFORGE_IMAGE` in `.env`.

## Credentials

**Yahoo** (read and/or send): Account Security → *Generate app password*. Use it as `password_env`.

**Gmail**: Google Cloud Console → new project → enable *Gmail API* → OAuth consent screen → create an
*OAuth client ID* (type *Desktop app*). Then:

```bash
pip install google-auth-oauthlib msal
python scripts/get_oauth_token.py google          # add --send only if delivery.method is "gmail"
```

> Apps left in *Testing* status get refresh tokens that expire after 7 days. Set the consent screen to *In production* (fine for personal use) to avoid this.

**Outlook / M365**: Entra ID → App registrations → new registration, *Allow public client flows = Yes*,
delegated permission `Mail.Read` (and `Mail.Send` for Graph delivery). Then:

```bash
python scripts/get_oauth_token.py microsoft       # device-code flow; add --tenant for work accounts
```

Put client IDs and refresh tokens into `.env` under the names referenced by `accounts.yaml`.

## FinOps

- Everything deterministic runs before any token is spent; typical noise (newsletters, receipts-by-bot, auto-replies) never reaches Claude.
- Haiku does the per-email work; Sonnet sees only compact JSON of surviving items.
- System prompts carry `cache_control: ephemeral`. (Anthropic only caches prefixes above a model-specific minimum length, so the short prompts may not hit the cache; telemetry shows cache read/write tokens so you can see.)
- Bodies are capped at 3,500 chars; batches are capped at 15 emails and ~80K estimated tokens.
- `max_daily_budget_usd` is a circuit breaker across all runs in a UTC day; hitting it defers the remaining mail and says so in the report.
- Every run stores tokens and cost in `run_metrics` and prints them in the report's **FinOps Run Telemetry** table.
- Prices in `llm/anthropic_sdk.py` are defaults — verify against current Anthropic pricing or override with `settings.pricing_per_mtok`. Unknown models are costed at the higher tier.
- No sampling parameters (`temperature`, `top_p`, `top_k`) are sent.

`llm_backend: "cli"` runs headless `claude -p --bare --tools ""` with the prompt on stdin; build with
`INSTALL_CLAUDE_CLI: "true"` in `docker-compose.yml`.

## Security notes

- Email content is untrusted: prompts treat it as data, the report HTML is escaped, and the model has no tools.
- Ofelia needs the Docker socket (mounted read-only), which is effectively host-level access to anything that can reach that container. Run on a machine you control, or replace Ofelia with host `cron` calling `docker compose exec mailforge-worker python -m mailforge.main`.
- Gmail uses `gmail.readonly`, Graph `Mail.Read`, Yahoo IMAP opens INBOX read-only: MailForge never marks mail as read.
- `.env`, `config/accounts.yaml`, `data/*.db` and `reports/*.md` are git-ignored.

## Development

```bash
pip install -r worker/requirements.txt pytest ruff && ruff check . && pytest -q
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for adding providers or delivery channels. MIT licensed.
