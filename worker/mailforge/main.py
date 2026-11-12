"""MailForge entrypoint: fetch -> filter -> dedupe -> triage -> synthesize -> save -> deliver."""
from __future__ import annotations

import argparse
import hashlib
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import delivery
from .config import ConfigError, load_config
from .hygiene import clean_body, filter_reason
from .llm.anthropic_sdk import Usage, estimate_tokens, format_email, make_batches, synthesize, triage
from .providers import PROVIDERS
from .storage import Store

log = logging.getLogger("mailforge")


def _err(e: Exception) -> str:
    return f"{type(e).__name__}: {str(e)[:200]}"


def fallback_markdown(items: list[dict]) -> str:
    """Deterministic report used when Stage 2 is skipped, over budget, or failed."""
    titles = {"ACTION": "Action Required", "DEADLINE": "Deadlines", "FINANCE": "Financials", "FYI": "FYI"}
    rank = {"HIGH": 0, "MED": 1, "LOW": 2}
    out = []
    for cat, title in titles.items():
        rows = sorted((i for i in items if i["cat"] == cat), key=lambda i: rank[i["urg"]])
        if rows:
            out.append(f"## {title}\n" + "\n".join(
                f"- **{i.get('subject', '')}** ({i.get('from', '')}) - {i.get('summary', '')}"
                + (f" _Action: {i['action_item']}_" if i.get("action_item") else "")
                + (f" _Due: {i['due_date']}_" if i.get("due_date") else "")
                + f" `[{i.get('account', '')}]`" for i in rows))
    return "\n\n".join(out) or "## Nothing needs your attention\nNo relevant new email."


def assemble(date: str, body: str, alerts: list[str], t: dict) -> str:
    parts = [f"# MailForge Daily Briefing — {date}"]
    if alerts:
        parts.append("> **⚠️ System Alerts**\n" + "\n".join(f"> - {a}" for a in alerts))
    parts.append(body.strip())
    parts.append(
        "## FinOps Run Telemetry\n"
        "| Metric | Value |\n|---|---|\n"
        f"| Fetched / pre-filtered / deduped | {t['fetched']} / {t['filtered']} / {t['deduped']} |\n"
        f"| Sent to triage / kept | {t['triaged']} / {t['kept']} |\n"
        f"| Tokens in / out | {t['input_tokens']} / {t['output_tokens']} |\n"
        f"| Cache read / write tokens | {t['cache_read']} / {t['cache_write']} |\n"
        f"| Run cost | ${t['cost_usd']:.4f} |"
    )
    return "\n\n".join(parts) + "\n"


def run(config_path: str, dry_run: bool = False, force: bool = False) -> int:
    cfg = load_config(config_path)
    s = cfg.settings
    data_dir, reports_dir = Path(os.environ.get("MAILFORGE_DATA", "/app/data")), Path(
        os.environ.get("MAILFORGE_REPORTS", "/app/reports"))
    store = Store(str(data_dir / "state.db"))
    now = datetime.now(UTC)
    since, date = now - timedelta(hours=s.lookback_hours), datetime.now().date().isoformat()
    alerts: list[str] = []

    # 1. Fetch (provider failures are isolated)
    fetched = []
    for acct in (a for a in cfg.accounts if a.enabled):
        try:
            msgs = PROVIDERS[acct.provider](acct).fetch_unread(since, s.max_emails_per_run)
            log.info("%s: %d unread", acct.id, len(msgs))
            fetched += msgs
        except Exception as e:  # noqa: BLE001 - any provider failure must not stop the run
            log.warning("%s failed: %s", acct.id, _err(e))
            alerts.append(f"`{acct.id}` ({acct.provider}) unavailable - {_err(e)}")

    # 2. Deterministic filters + dedup
    stats = dict(fetched=len(fetched), filtered=0, deduped=0, triaged=0, kept=0,
                 input_tokens=0, output_tokens=0, cache_read=0, cache_write=0, cost_usd=0.0)
    cands = []  # (msg, body, hash)
    seen_hashes: set[str] = set()
    for m in sorted(fetched, key=lambda m: m.date, reverse=True):
        if filter_reason(m, s):
            stats["filtered"] += 1
            continue
        body = clean_body(m)
        h = hashlib.sha256(f"{m.subject}\n{body}".encode()).hexdigest()
        if not force and (store.seen(m.account_id, m.message_id) or store.hash_seen(h)) or h in seen_hashes:
            stats["deduped"] += 1
            continue
        seen_hashes.add(h)
        cands.append((m, body, h))
    cands = cands[: s.max_emails_per_run]

    if dry_run:
        for m, body, _ in cands:
            print(f"[{m.account_id}] {m.sender} | {m.subject} | ~{estimate_tokens(body)} tok")
        print(f"dry-run: {stats['fetched']} fetched, {stats['filtered']} filtered, "
              f"{stats['deduped']} deduped, {len(cands)} would go to Claude; alerts: {alerts}")
        return 0
    if not cands and not alerts and not force:
        log.info("No new mail; nothing to report.")
        return 0

    # 3. Stage 1: triage (Haiku)
    total, kept = Usage(), []
    entries = [(f"e{i}", m, format_email(f"e{i}", m, body)) for i, (m, body, _) in enumerate(cands)]
    by_id = {e[0]: (m, h) for e, (m, _, h) in zip(entries, cands, strict=True)}
    complete = None
    if entries:
        try:
            if s.llm_backend == "cli":
                from .llm.claude_cli import CliClient
                complete = CliClient(s.pricing_per_mtok).complete
            else:
                from .llm.anthropic_sdk import SdkClient
                complete = SdkClient(s.pricing_per_mtok).complete
        except Exception as e:  # noqa: BLE001
            alerts.append(f"LLM backend unavailable - {_err(e)}")

    def over_budget() -> bool:  # circuit breaker on daily spend
        return not force and store.spent_today() + total.cost >= s.max_daily_budget_usd

    for batch in make_batches(entries) if complete else []:
        if over_budget():
            alerts.append(f"Daily budget ${s.max_daily_budget_usd:.2f} reached; remaining emails deferred to next run")
            break
        try:
            items, u = triage(complete, s.triage_model, batch)
        except Exception as e:  # noqa: BLE001 - batch stays unprocessed and is retried next run
            alerts.append(f"Triage batch failed ({len(batch)} emails, will retry) - {_err(e)}")
            continue
        total.add(u)
        for it in items:
            m, _ = by_id[it["id"]]
            it.update({"from": m.sender[:40], "subject": m.subject[:80], "account": m.account_id})
        kept += items
        stats["triaged"] += len(batch)
        for e in batch:
            m, h = by_id[e[0]]
            store.mark(m.account_id, m.message_id, m.thread_id, h)

    # 4. Stage 2: synthesis (Sonnet)
    if kept and complete and not over_budget():
        try:
            body, u = synthesize(complete, s.synthesis_model, [{k: v for k, v in i.items() if k != "id"} for i in kept])
            total.add(u)
        except Exception as e:  # noqa: BLE001
            alerts.append(f"Synthesis failed, using plain digest - {_err(e)}")
            body = fallback_markdown(kept)
    else:
        if kept:
            alerts.append("Synthesis skipped (budget/backend); plain digest used")
        body = fallback_markdown(kept)

    stats.update(kept=len(kept), input_tokens=total.input, output_tokens=total.output,
                 cache_read=total.cache_read, cache_write=total.cache_write, cost_usd=total.cost)

    # 5. Persist first, then deliver
    report = assemble(date, body, alerts, stats)
    reports_dir.mkdir(parents=True, exist_ok=True)
    path = reports_dir / f"{date}-digest.md"
    path.write_text(report)
    log.info("Report saved: %s (cost $%.4f)", path, total.cost)
    store.record_run(date, alerts=len(alerts), **stats)

    rc = 0
    if cfg.delivery.enabled:
        try:
            delivery.send(report, date, cfg.delivery)
            log.info("Report emailed.")
        except Exception as e:  # noqa: BLE001
            log.error("Delivery failed (report kept on disk): %s", _err(e))
            rc = 2
    return rc


def main() -> None:
    p = argparse.ArgumentParser(prog="mailforge")
    p.add_argument("--config", default=os.environ.get("MAILFORGE_CONFIG", "/app/config/accounts.yaml"))
    p.add_argument("--dry-run", action="store_true", help="fetch+filter only; no LLM, no state, no delivery")
    p.add_argument("--force", action="store_true", help="ignore dedup state and the daily budget")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        sys.exit(run(a.config, a.dry_run, a.force))
    except ConfigError as e:
        log.error("%s", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
