# Contributing to MailForge

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r worker/requirements.txt pytest ruff
ruff check . && pytest -q
```

CI runs the same plus a Docker build. Keep PRs small; add a test for any filtering/FinOps logic you change.

## Adding an email provider

1. Create `worker/mailforge/providers/<name>.py` with a class extending `EmailProvider`
   and implement `fetch_unread(since, limit) -> list[EmailMessage]`.
   - Lower-case header names; fill `headers` with at least `list-unsubscribe`, `precedence`, `auto-submitted` if the API exposes them.
   - Never mark mail as read. Read secrets only via `config.env(name)`.
   - Raise on failure; `main.py` isolates it into the System Alerts banner.
2. Register it in `providers/__init__.py` (`PROVIDERS`).
3. Add the name to `Account.provider` and its required `*_env` fields to the validator in `config.py`.
4. Document an example in `config/accounts.example.yaml` and `.env.example`.

## Adding a delivery channel

1. Add a branch in `delivery.send()` and the method name to `Delivery.method` in `config.py`.
2. Reuse `build_message()` / `render_html()`; always set the `X-MailForge-Report: true` header
   (loop prevention) and the `[MailForge] Daily Briefing` subject.

## Rules

- No secrets, personal addresses or tokens in code, configs, tests or logs.
- No sampling parameters (`temperature`, `top_p`, `top_k`) in API calls.
- Anything that can be decided without an LLM must be decided before the LLM (`hygiene.py`).
