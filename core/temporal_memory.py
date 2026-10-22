"""
Continuous Temporal Memory & Activity Timeline RAG Engine for SpaceV.
Tracks timestamped clipboard copies and active window focus history in a local,
transactional SQLite FTS5 database with automatic privacy redaction of passwords and API keys.
"""
from __future__ import annotations

import re
import time
import json
import sqlite3
import logging
import threading
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

import pyperclip

logger = logging.getLogger("SpaceV.TemporalMemory")

DB_PATH = Path(__file__).resolve().parent.parent / "spacev_temporal_memory.db"

# Automated privacy pattern redaction
SENSITIVE_PATTERNS = [
    re.compile(r"(sk-[a-zA-Z0-9_-]{20,})", re.IGNORECASE),
    re.compile(r"(ghp_[a-zA-Z0-9]{20,})", re.IGNORECASE),
    re.compile(r"(password\s*[:=]\s*)['\"]?([^'\"\s\n]{4,})['\"]?", re.IGNORECASE),
    re.compile(r"(bearer\s+)([a-zA-Z0-9_\-\.]{20,})", re.IGNORECASE),
    re.compile(r"(api[_-]?key\s*[:=]\s*)['\"]?([^'\"\s\n]{10,})['\"]?", re.IGNORECASE),
]


def sanitize_text(text: str) -> str:
    """Masks secrets, passwords, and sensitive tokens from continuous memory."""
    sanitized = text
    for pattern in SENSITIVE_PATTERNS:
        sanitized = pattern.sub(r"\1***REDACTED***", sanitized)
    return sanitized


class TemporalMemoryEngine:
    """
    Continuous Temporal Event Stream & Full-Text Search Database.
    Indexes user workflow events (clipboard, active windows, agent actions).
    """

    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._lock = threading.Lock()
        self._tracker_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._last_clipboard = ""
        self._last_window = ""
        self._init_db()

    def _init_db(self) -> None:
        """Initializes relational and FTS5 SQLite tables."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS temporal_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL,
                    iso_time TEXT,
                    event_type TEXT,
                    title TEXT,
                    content TEXT,
                    metadata_json TEXT
                )
            """)
            try:
                cursor.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS temporal_events_fts USING fts5(
                        title,
                        content,
                        event_type,
                        content='temporal_events',
                        content_rowid='id',
                        tokenize='porter unicode61'
                    )
                """)
            except Exception:
                pass
            conn.commit()
            conn.close()

    def record_event(
        self,
        event_type: str,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> int:
        """Stores a workflow event with automatic secret sanitization."""
        clean_content = sanitize_text(content)
        clean_title = sanitize_text(title)
        meta_str = json.dumps(metadata or {})
        now_ts = time.time()
        iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO temporal_events (timestamp, iso_time, event_type, title, content, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (now_ts, iso, event_type, clean_title, clean_content, meta_str)
            )
            row_id = cursor.lastrowid
            try:
                cursor.execute(
                    """
                    INSERT INTO temporal_events_fts (rowid, title, content, event_type)
                    VALUES (?, ?, ?, ?)
                    """,
                    (row_id, clean_title, clean_content, event_type)
                )
            except Exception:
                pass
            conn.commit()
            conn.close()

        return row_id

    def search_events(
        self,
        query: str,
        event_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        clean_q = re.sub(r"[^\w\s]", "", query).strip()
        words = [w for w in clean_q.split() if w]
        if not words:
            return []
        fts_match_expr = " OR ".join(f"{w}*" for w in words)

        results = []
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            cursor = conn.cursor()
            try:
                # FTS5 ranking
                type_filter = f"AND e.event_type = '{event_type}'" if event_type else ""
                sql = f"""
                    SELECT e.id, e.iso_time, e.event_type, e.title, e.content, e.metadata_json
                    FROM temporal_events_fts f
                    JOIN temporal_events e ON f.rowid = e.id
                    WHERE temporal_events_fts MATCH ? {type_filter}
                    ORDER BY bm25(temporal_events_fts), e.timestamp DESC
                    LIMIT ?
                """
                cursor.execute(sql, (fts_match_expr, limit))
                rows = cursor.fetchall()
            except Exception:
                # Fallback LIKE
                like_term = f"%{clean_q}%"
                if event_type:
                    cursor.execute(
                        """
                        SELECT id, iso_time, event_type, title, content, metadata_json
                        FROM temporal_events
                        WHERE (content LIKE ? OR title LIKE ?) AND event_type = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (like_term, like_term, event_type, limit)
                    )
                else:
                    cursor.execute(
                        """
                        SELECT id, iso_time, event_type, title, content, metadata_json
                        FROM temporal_events
                        WHERE content LIKE ? OR title LIKE ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                        """,
                        (like_term, like_term, limit)
                    )
                rows = cursor.fetchall()

            for r in rows:
                results.append({
                    "id": r[0],
                    "time": r[1],
                    "type": r[2],
                    "title": r[3],
                    "content": r[4],
                    "metadata": json.loads(r[5]) if r[5] else {}
                })
            conn.close()

        return results

    def get_recent_clipboard(self, limit: int = 5) -> List[Dict[str, Any]]:
        """Retrieves most recent clipboard history entries."""
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, iso_time, content, title
                FROM temporal_events
                WHERE event_type = 'clipboard'
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,)
            )
            rows = cursor.fetchall()
            conn.close()

        return [{"id": r[0], "time": r[1], "content": r[2], "title": r[3]} for r in rows]

    def get_timeline(self, minutes: int = 60, limit: int = 20) -> List[Dict[str, Any]]:
        """Retrieves activity timeline for the past N minutes."""
        min_ts = time.time() - (minutes * 60)
        with self._lock:
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, iso_time, event_type, title, content
                FROM temporal_events
                WHERE timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (min_ts, limit)
            )
            rows = cursor.fetchall()
            conn.close()

        return [{"id": r[0], "time": r[1], "type": r[2], "title": r[3], "content": r[4]} for r in rows]

    def poll_activity(self) -> None:
        """Polls active window title and clipboard changes once."""
        try:
            # 1. Clipboard tracking
            current_clip = pyperclip.paste().strip()
            if current_clip and current_clip != self._last_clipboard and len(current_clip) > 3:
                self._last_clipboard = current_clip
                preview = current_clip[:60] + ("..." if len(current_clip) > 60 else "")
                self.record_event(
                    event_type="clipboard",
                    title=f"Copied: {preview}",
                    content=current_clip,
                    metadata={"length": len(current_clip)}
                )

            # 2. Window focus tracking
            from tools.vision_tools import get_active_window_info
            current_win = get_active_window_info()
            if current_win and current_win != self._last_window:
                self._last_window = current_win
                self.record_event(
                    event_type="window_focus",
                    title=current_win,
                    content=current_win
                )
        except Exception:
            pass

    def start_tracker(self, poll_interval_sec: float = 3.0) -> None:
        """Starts background tracking thread with low CPU usage."""
        if self._tracker_thread and self._tracker_thread.is_alive():
            return

        self._stop_event.clear()

        def _worker():
            while not self._stop_event.is_set():
                self.poll_activity()
                time.sleep(poll_interval_sec)

        self._tracker_thread = threading.Thread(target=_worker, daemon=True, name="SpaceV-TemporalTracker")
        self._tracker_thread.start()
        logger.info("[TemporalMemory] 🕰️ Continuous activity & clipboard timeline tracker active.")

    def stop_tracker(self) -> None:
        """Stops the background tracking thread."""
        self._stop_event.set()
        if self._tracker_thread:
            self._tracker_thread.join(timeout=1.0)


# Global singleton
temporal_memory = TemporalMemoryEngine()
