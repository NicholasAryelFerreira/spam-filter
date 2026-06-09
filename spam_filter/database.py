from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterator

from spam_filter.models import FinalDecision


class Database:
    def __init__(self, path: str) -> None:
        self.path = path
        parent = Path(path).expanduser().resolve().parent
        parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS processed_messages (
                    message_id TEXT PRIMARY KEY,
                    internet_message_id TEXT,
                    action TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    sender_email TEXT NOT NULL,
                    processed_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    sender_email TEXT NOT NULL,
                    subject_hash TEXT NOT NULL,
                    classification TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    model TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS blocked_senders (
                    sender_email TEXT PRIMARY KEY,
                    source TEXT NOT NULL,
                    note TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS graph_subscriptions (
                    subscription_id TEXT PRIMARY KEY,
                    resource TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def is_processed(self, message_id: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM processed_messages WHERE message_id = ?",
                (message_id,),
            ).fetchone()
            return row is not None

    def record_processed(
        self,
        message_id: str,
        internet_message_id: str | None,
        sender_email: str,
        decision: FinalDecision,
    ) -> None:
        now = datetime.now(UTC).isoformat()
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO processed_messages
                (message_id, internet_message_id, action, classification, confidence, sender_email, processed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    internet_message_id,
                    decision.action,
                    decision.classification,
                    decision.confidence,
                    sender_email,
                    now,
                ),
            )

    def record_decision(
        self,
        message_id: str,
        sender_email: str,
        subject_hash: str,
        decision: FinalDecision,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO decisions
                (message_id, sender_email, subject_hash, classification, confidence, action, reason, model, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    sender_email,
                    subject_hash,
                    decision.classification,
                    decision.confidence,
                    decision.action,
                    decision.reason,
                    decision.model,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def recent_decisions(self, limit: int = 50) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT message_id, sender_email, subject_hash, classification, confidence, action, reason, model, created_at
                FROM decisions
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def add_blocked_sender(self, sender_email: str, source: str, note: str = "") -> None:
        normalized = sender_email.strip().lower()
        if not normalized:
            raise ValueError("sender_email is required")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO blocked_senders (sender_email, source, note, created_at)
                VALUES (?, ?, ?, COALESCE(
                    (SELECT created_at FROM blocked_senders WHERE sender_email = ?),
                    ?
                ))
                """,
                (normalized, source, note, normalized, datetime.now(UTC).isoformat()),
            )

    def remove_blocked_sender(self, sender_email: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "DELETE FROM blocked_senders WHERE sender_email = ?",
                (sender_email.strip().lower(),),
            )

    def is_blocked_sender(self, sender_email: str) -> bool:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM blocked_senders WHERE sender_email = ?",
                (sender_email.strip().lower(),),
            ).fetchone()
            return row is not None

    def list_blocked_senders(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT sender_email, created_at, source, note
                FROM blocked_senders
                ORDER BY created_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]

    def upsert_subscription(self, subscription_id: str, resource: str, expires_at: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO graph_subscriptions
                (subscription_id, resource, expires_at, updated_at)
                VALUES (?, ?, ?, ?)
                """,
                (subscription_id, resource, expires_at, datetime.now(UTC).isoformat()),
            )

    def subscriptions(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT subscription_id, resource, expires_at, updated_at
                FROM graph_subscriptions
                ORDER BY updated_at DESC
                """
            ).fetchall()
            return [dict(row) for row in rows]
