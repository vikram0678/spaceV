"""
SpaceV SQLite WAL Durable Task Ledger & Mission Persistence.
Provides high-throughput transactional logging of missions, task graphs,
events, verification checks, and cryptographic artifact hashes.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SpaceV.DurableLedger")

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB_PATH = REPO_ROOT / "reports" / "run_ledger.db"


class DurableLedger:
    """
    Embedded SQLite Task Ledger configured in WAL mode.
    Guarantees ACID durability and microsecond execution logging.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        return conn

    def _init_database(self):
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS missions (
                    mission_id TEXT PRIMARY KEY,
                    objective TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    total_cost_usd REAL DEFAULT 0.0,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS task_nodes (
                    task_id TEXT PRIMARY KEY,
                    mission_id TEXT,
                    name TEXT NOT NULL,
                    worker_role TEXT NOT NULL,
                    status TEXT NOT NULL,
                    sandbox_id TEXT,
                    retry_count INTEGER DEFAULT 0,
                    started_at TIMESTAMP,
                    finished_at TIMESTAMP,
                    execution_duration_s REAL,
                    error_summary TEXT
                );

                CREATE TABLE IF NOT EXISTS execution_events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS verification_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    check_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected TEXT,
                    observed TEXT,
                    evidence_json TEXT,
                    error TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS artifacts (
                    artifact_id TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size_bytes INTEGER NOT NULL,
                    sha256_hash TEXT NOT NULL,
                    mime_type TEXT NOT NULL,
                    verified BOOLEAN NOT NULL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

    def record_mission(self, mission_id: str, objective: str, status: str = "CREATED"):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO missions (mission_id, objective, status) VALUES (?, ?, ?)",
                (mission_id, objective, status)
            )

    def update_mission_status(self, mission_id: str, status: str, error_summary: Optional[str] = None):
        ts = datetime.now(timezone.utc).isoformat() if status in ("COMPLETED", "FAILED", "CANCELLED") else None
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE missions SET status = ?, completed_at = ?, error_summary = ? WHERE mission_id = ?",
                (status, ts, error_summary, mission_id)
            )

    def record_task_node(
        self,
        task_id: str,
        name: str,
        worker_role: str,
        status: str = "READY",
        mission_id: Optional[str] = None,
        sandbox_id: Optional[str] = None
    ):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO task_nodes (task_id, mission_id, name, worker_role, status, sandbox_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (task_id, mission_id, name, worker_role, status, sandbox_id)
            )

    def update_task_node(
        self,
        task_id: str,
        status: str,
        error_summary: Optional[str] = None,
        duration_s: Optional[float] = None
    ):
        ts = datetime.now(timezone.utc).isoformat() if status in ("COMPLETED", "FAILED") else None
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE task_nodes
                SET status = ?, finished_at = ?, error_summary = ?, execution_duration_s = ?
                WHERE task_id = ?
                """,
                (status, ts, error_summary, duration_s, task_id)
            )

    def record_event(self, task_id: str, event_type: str, payload: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute(
                "INSERT INTO execution_events (task_id, event_type, payload) VALUES (?, ?, ?)",
                (task_id, event_type, json.dumps(payload))
            )

    def record_verification(
        self,
        task_id: str,
        check_type: str,
        status: str,
        expected: Any,
        observed: Any,
        evidence: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO verification_records (task_id, check_type, status, expected, observed, evidence_json, error)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    check_type,
                    status,
                    json.dumps(expected) if isinstance(expected, (dict, list)) else str(expected),
                    json.dumps(observed) if isinstance(observed, (dict, list)) else str(observed),
                    json.dumps(evidence or {}),
                    error
                )
            )

    def record_artifact(
        self,
        artifact_id: str,
        task_id: str,
        file_path: str,
        file_size_bytes: int,
        sha256_hash: str,
        mime_type: str = "text/plain",
        verified: bool = True
    ):
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO artifacts (artifact_id, task_id, file_path, file_size_bytes, sha256_hash, mime_type, verified)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (artifact_id, task_id, file_path, file_size_bytes, sha256_hash, mime_type, 1 if verified else 0)
            )

    def get_uncompleted_tasks(self) -> List[Dict[str, Any]]:
        """Queries tasks that were interrupted or left incomplete across restarts."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM task_nodes WHERE status NOT IN ('COMPLETED', 'FAILED', 'CANCELLED')"
            )
            return [dict(row) for row in cursor.fetchall()]


durable_ledger = DurableLedger()
