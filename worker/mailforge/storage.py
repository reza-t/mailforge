"""SQLite state: processed-email dedup + per-run FinOps telemetry."""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

SCHEMA = """
CREATE TABLE IF NOT EXISTS processed_emails (
    account_id   TEXT NOT NULL,
    message_id   TEXT NOT NULL,
    thread_id    TEXT,
    content_hash TEXT NOT NULL,
    processed_at TEXT NOT NULL,
    PRIMARY KEY (account_id, message_id)
);
CREATE INDEX IF NOT EXISTS idx_hash ON processed_emails(content_hash);
CREATE TABLE IF NOT EXISTS run_metrics (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_date TEXT NOT NULL, ts TEXT NOT NULL,
    fetched INT, filtered INT, deduped INT, triaged INT, kept INT,
    input_tokens INT, output_tokens INT, cache_read_tokens INT, cache_write_tokens INT,
    cost_usd REAL, alerts INT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: str):
        self.db = sqlite3.connect(path)
        self.db.executescript(SCHEMA)

    def seen(self, account_id: str, message_id: str) -> bool:
        return self.db.execute(
            "SELECT 1 FROM processed_emails WHERE account_id=? AND message_id=?",
            (account_id, message_id),
        ).fetchone() is not None

    def hash_seen(self, content_hash: str) -> bool:
        """Same content already processed (e.g. one mail delivered to two accounts)."""
        return self.db.execute(
            "SELECT 1 FROM processed_emails WHERE content_hash=?", (content_hash,)
        ).fetchone() is not None

    def mark(self, account_id: str, message_id: str, thread_id: str, content_hash: str) -> None:
        self.db.execute(
            "INSERT OR IGNORE INTO processed_emails VALUES (?,?,?,?,?)",
            (account_id, message_id, thread_id, content_hash, _now()),
        )
        self.db.commit()

    def spent_today(self) -> float:
        today = datetime.now(UTC).date().isoformat()
        row = self.db.execute(
            "SELECT COALESCE(SUM(cost_usd),0) FROM run_metrics WHERE substr(ts,1,10)=?", (today,)
        ).fetchone()
        return float(row[0])

    def record_run(self, run_date: str, **m) -> None:
        self.db.execute(
            "INSERT INTO run_metrics (run_date, ts, fetched, filtered, deduped, triaged, kept,"
            " input_tokens, output_tokens, cache_read_tokens, cache_write_tokens, cost_usd, alerts)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_date, _now(), m["fetched"], m["filtered"], m["deduped"], m["triaged"], m["kept"],
             m["input_tokens"], m["output_tokens"], m["cache_read"], m["cache_write"],
             m["cost_usd"], m["alerts"]),
        )
        self.db.commit()
