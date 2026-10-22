"""
SpaceV Database Access Layer for PostgreSQL Ledger.
Handles connection pooling and idempotent queries.
"""
from __future__ import annotations

import logging
from typing import List, Dict, Any, Optional
import psycopg
from psycopg.rows import dict_row

from spacev.config import settings

logger = logging.getLogger("SpaceV.Database")

# In-memory store fallback for standalone test harnesses when Postgres is offline
_MEMORY_RUNS: List[Dict[str, Any]] = [
    {
        "id": 1,
        "run_id": "run-seed-001",
        "sandbox_name": "sbx-seeddemo1",
        "problem_id": "prob-spacev-detonation",
        "state": "deleted",
        "execution_target": "celesto_sandbox",
        "created_at": "2026-10-22T05:00:00Z"
    }
]


class DatabaseManager:
    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or settings.database_url

    def get_connection(self):
        return psycopg.connect(self.db_url, row_factory=dict_row)

    def is_connected(self) -> bool:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                    return True
        except Exception:
            return False

    def list_runs(self) -> List[Dict[str, Any]]:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT id, run_id, sandbox_name, problem_id, state, execution_target, created_at FROM runs ORDER BY id ASC")
                    rows = cur.fetchall()
                    for r in rows:
                        if "created_at" in r and r["created_at"]:
                            r["created_at"] = str(r["created_at"])
                    return rows
        except Exception as e:
            logger.warning(f"Using in-memory fallback ledger: {e}")
            return list(_MEMORY_RUNS)

    def insert_run(self, run_id: str, sandbox_name: str, problem_id: str, state: str, execution_target: str) -> Dict[str, Any]:
        try:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO runs (run_id, sandbox_name, problem_id, state, execution_target)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (sandbox_name) DO UPDATE SET
                            state = EXCLUDED.state,
                            execution_target = EXCLUDED.execution_target
                        RETURNING id, run_id, sandbox_name, problem_id, state, execution_target, created_at
                        """,
                        (run_id, sandbox_name, problem_id, state, execution_target)
                    )
                    row = cur.fetchone()
                    conn.commit()
                    if row and "created_at" in row and row["created_at"]:
                        row["created_at"] = str(row["created_at"])
                    return row
        except Exception as e:
            logger.warning(f"Postgres insert failed, appending to memory ledger: {e}")
            new_entry = {
                "id": len(_MEMORY_RUNS) + 1,
                "run_id": run_id,
                "sandbox_name": sandbox_name,
                "problem_id": problem_id,
                "state": state,
                "execution_target": execution_target,
                "created_at": "2026-10-22T05:00:00Z"
            }
            _MEMORY_RUNS.append(new_entry)
            return new_entry


db = DatabaseManager()
