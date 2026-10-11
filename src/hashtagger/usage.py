"""Freemium usage store — enforces the daily generation limit (architecture §3).

Tables (architecture §3):
  accounts(id, email, tier, created_at)
  usage_counters(account_id, day, generate_count)

Free tier: FREE_DAILY_LIMIT generations/day. Pro tier: unlimited.
Counters are keyed by (account_id, day) so the limit resets each UTC day.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

FREE_DAILY_LIMIT = 10
TIERS = ("free", "pro")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id         TEXT PRIMARY KEY,
    email      TEXT,
    tier       TEXT NOT NULL DEFAULT 'free',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usage_counters (
    account_id     TEXT NOT NULL,
    day            TEXT NOT NULL,
    generate_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (account_id, day)
);
"""


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _reset_at() -> str:
    """Next UTC midnight, ISO-8601."""
    now = datetime.now(timezone.utc)
    tomorrow = now.replace(hour=0, minute=0, second=0, microsecond=0)
    from datetime import timedelta

    return (tomorrow + timedelta(days=1)).isoformat()


class UsageStore:
    """SQLite-backed per-account usage counters and tier lookup."""

    def __init__(self, db_path: str = ":memory:") -> None:
        self._lock = threading.Lock()
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _ensure_account(self, account_id: str) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO accounts (id, tier, created_at) VALUES (?,?,?)",
            (account_id, "free", datetime.now(timezone.utc).isoformat()),
        )

    def tier(self, account_id: str) -> str:
        with self._lock:
            self._ensure_account(account_id)
            row = self._conn.execute(
                "SELECT tier FROM accounts WHERE id = ?", (account_id,)
            ).fetchone()
            self._conn.commit()
        return row["tier"] if row else "free"

    def set_tier(self, account_id: str, tier: str) -> None:
        if tier not in TIERS:
            raise ValueError(f"tier must be one of {TIERS}")
        with self._lock:
            self._ensure_account(account_id)
            self._conn.execute("UPDATE accounts SET tier = ? WHERE id = ?", (tier, account_id))
            self._conn.commit()

    def used_today(self, account_id: str) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT generate_count FROM usage_counters WHERE account_id = ? AND day = ?",
                (account_id, _today()),
            ).fetchone()
        return int(row["generate_count"]) if row else 0

    def increment(self, account_id: str) -> int:
        with self._lock:
            self._ensure_account(account_id)
            self._conn.execute(
                "INSERT INTO usage_counters (account_id, day, generate_count) VALUES (?,?,1)"
                " ON CONFLICT(account_id, day) DO UPDATE SET generate_count = generate_count + 1",
                (account_id, _today()),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT generate_count FROM usage_counters WHERE account_id = ? AND day = ?",
                (account_id, _today()),
            ).fetchone()
        return int(row["generate_count"])

    def can_generate(self, account_id: str) -> bool:
        if self.tier(account_id) == "pro":
            return True
        return self.used_today(account_id) < FREE_DAILY_LIMIT

    def summary(self, account_id: str) -> dict:
        tier = self.tier(account_id)
        used = self.used_today(account_id)
        return {
            "tier": tier,
            "used_today": used,
            "limit": FREE_DAILY_LIMIT if tier == "free" else None,
            "reset_at": _reset_at(),
        }

    def close(self) -> None:
        self._conn.close()
