"""
SpaceV Ambient File System Watcher (Volume I §4.4 & Volume III §24).
Monitors workspace file modifications, creations, and deletions in real-time.
Features:
  - Debounces rapid bursts (default 500ms window)
  - Filters noisy directories (.git, node_modules, __pycache__, .venv)
  - Automatic classification: code (.py, .ts, .js), config (.yaml, .toml, .json), and test files
  - Dual-mode execution: native watchdog inotify kernel observer when available,
    with an internal zero-dependency asyncio fallback scanner when running in minimal environments.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import logging
from pathlib import Path
import time

logger = logging.getLogger("SpaceV.FSWatcher")

DEFAULT_IGNORE_PATTERNS: set[str] = {
    ".git", "__pycache__", "node_modules", ".venv", "venv",
    ".ruff_cache", ".pytest_cache", ".mypy_cache", "dist",
    "build", ".tox", ".eggs", "*.pyc", "*.pyo", ".spacev"
}

WATCH_EXTENSIONS: set[str] = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".html", ".css",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
    ".sh", ".bash", ".sql", ".env",
}


@dataclass
class FileChangeEvent:
    """Structured event emitted when a watched file undergoes a change."""
    event_type: str          # "created" | "modified" | "deleted" | "moved"
    file_path: str           # Absolute path
    relative_path: str       # Path relative to watch root
    extension: str           # e.g., ".py"
    size_bytes: int          # File size after change (0 if deleted)
    timestamp: float         # Unix timestamp
    is_directory: bool       # True if directory

    # Classification flags
    is_code_file: bool = False
    is_config_file: bool = False
    is_test_file: bool = False

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "file_path": self.file_path,
            "relative_path": self.relative_path,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "timestamp": self.timestamp,
            "is_directory": self.is_directory,
            "is_code_file": self.is_code_file,
            "is_config_file": self.is_config_file,
            "is_test_file": self.is_test_file,
        }


class _WatchdogBridge:
    """Bridge for watchdog event handler when watchdog package is installed."""

    def __init__(self, watcher: SpaceVFileWatcher):
        self.watcher = watcher

    def dispatch(self, event):
        event_map = {
            "created": "created",
            "modified": "modified",
            "deleted": "deleted",
            "moved": "moved",
        }
        event_type = event_map.get(event.event_type, "modified")
        src_path = getattr(event, "dest_path", None) if event_type == "moved" else event.src_path
        self.watcher._handle_fs_event(event_type, src_path)


class SpaceVFileWatcher:
    """
    Ambient file system observer.
    Emits debounced FileChangeEvent objects to on_event callback or EventBus.
    """

    def __init__(
        self,
        watch_paths: list[str | Path],
        on_event: Callable[[FileChangeEvent], None] | None = None,
        debounce_ms: int = 500,
        ignore_patterns: set[str] | None = None,
    ):
        self.watch_paths = [Path(p).resolve() for p in watch_paths]
        self.on_event = on_event
        self.debounce_ms = debounce_ms
        self.ignore_patterns = set(ignore_patterns) if ignore_patterns else set(DEFAULT_IGNORE_PATTERNS)
        self._last_events: dict[str, float] = {}
        self._running = False
        self._watchdog_observer = None
        self._poll_task: asyncio.Task | None = None
        self._file_snapshots: dict[str, tuple[float, int]] = {}  # path -> (mtime, size)

    def _should_ignore(self, path: Path) -> bool:
        """Determines if path matches any ignore patterns."""
        parts = path.parts
        for pattern in self.ignore_patterns:
            if pattern in parts:
                return True
            if pattern.startswith("*") and path.suffix == pattern[1:]:
                return True
        return False

    def _classify_file(self, path: Path) -> dict[str, bool]:
        """Classifies a file by extension and path semantics."""
        name = path.name.lower()
        ext = path.suffix.lower()
        return {
            "is_code_file": ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".c", ".cpp"},
            "is_config_file": ext in {".json", ".yaml", ".yml", ".toml", ".env", ".ini", ".xml"} or name in {"dockerfile", "makefile"},
            "is_test_file": name.startswith("test_") or name.endswith("_test.py") or "tests" in path.parts,
        }

    def _debounce_check(self, file_path: str) -> bool:
        """Enforces debouncing window to avoid flooding events during rapid writes."""
        now = time.time()
        last = self._last_events.get(file_path, 0.0)
        if (now - last) * 1000.0 < self.debounce_ms:
            return False
        self._last_events[file_path] = now
        return True

    def _handle_fs_event(self, event_type: str, src_path: str):
        """Translates raw filesystem path into a structured FileChangeEvent."""
        path = Path(src_path)
        if self._should_ignore(path):
            return

        if not path.is_dir() and path.suffix.lower() not in WATCH_EXTENSIONS:
            return

        if not self._debounce_check(src_path):
            return

        classification = self._classify_file(path)
        relative = str(path)
        for root in self.watch_paths:
            try:
                relative = str(path.relative_to(root))
                break
            except ValueError:
                continue

        try:
            size = path.stat().st_size if path.exists() else 0
        except OSError:
            size = 0

        event = FileChangeEvent(
            event_type=event_type,
            file_path=str(path),
            relative_path=relative,
            extension=path.suffix.lower(),
            size_bytes=size,
            timestamp=time.time(),
            is_directory=path.is_dir() if path.exists() else False,
            **classification,
        )

        logger.debug(f"[FS_WATCH] {event_type.upper()}: {relative}")
        if self.on_event:
            try:
                self.on_event(event)
            except Exception as e:
                logger.error(f"[FS_WATCH] Error in on_event callback: {e}")

    async def start(self):
        """Starts ambient file watching."""
        self._running = True

        # Try watchdog first
        has_watchdog = False
        try:
            from watchdog.observers import Observer
            self._watchdog_observer = Observer()
            handler = _WatchdogBridge(self)
            for wp in self.watch_paths:
                if wp.exists() and wp.is_dir():
                    self._watchdog_observer.schedule(handler, str(wp), recursive=True)
            self._watchdog_observer.start()
            has_watchdog = True
            logger.info(f"[FS_WATCH] Native watchdog observer started for {len(self.watch_paths)} paths")
        except ImportError:
            logger.info("[FS_WATCH] watchdog not installed; starting native asyncio polling watcher")

        if not has_watchdog:
            # Snapshot initial directory state
            self._take_snapshot()
            self._poll_task = asyncio.create_task(self._poll_loop())
            logger.info(f"[FS_WATCH] Asyncio polling observer started for {len(self.watch_paths)} paths")

    def _take_snapshot(self):
        """Snapshots current files for poll-based delta detection."""
        for wp in self.watch_paths:
            if not wp.exists() or not wp.is_dir():
                continue
            for p in wp.rglob("*"):
                if self._should_ignore(p) or p.is_dir():
                    continue
                if p.suffix.lower() in WATCH_EXTENSIONS:
                    try:
                        stat = p.stat()
                        self._file_snapshots[str(p)] = (stat.st_mtime, stat.st_size)
                    except OSError:
                        pass

    async def _poll_loop(self):
        """Lightweight background polling loop when watchdog is not installed."""
        while self._running:
            try:
                await asyncio.sleep(max(0.5, self.debounce_ms / 1000.0))
                current_files: set[str] = set()

                for wp in self.watch_paths:
                    if not wp.exists() or not wp.is_dir():
                        continue
                    for p in wp.rglob("*"):
                        if self._should_ignore(p) or p.is_dir():
                            continue
                        if p.suffix.lower() not in WATCH_EXTENSIONS:
                            continue

                        p_str = str(p)
                        current_files.add(p_str)
                        try:
                            stat = p.stat()
                            mtime, size = stat.st_mtime, stat.st_size
                            if p_str not in self._file_snapshots:
                                self._file_snapshots[p_str] = (mtime, size)
                                self._handle_fs_event("created", p_str)
                            elif self._file_snapshots[p_str] != (mtime, size):
                                self._file_snapshots[p_str] = (mtime, size)
                                self._handle_fs_event("modified", p_str)
                        except OSError:
                            continue

                # Check for deletions
                deleted = set(self._file_snapshots.keys()) - current_files
                for del_path in deleted:
                    del self._file_snapshots[del_path]
                    self._handle_fs_event("deleted", del_path)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"[FS_WATCH] Poll error: {e}")

    async def stop(self):
        """Stops the file watcher."""
        self._running = False
        if self._watchdog_observer:
            try:
                self._watchdog_observer.stop()
                self._watchdog_observer.join(timeout=2)
            except Exception:
                pass
            self._watchdog_observer = None

        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None

        logger.info("[FS_WATCH] File watcher stopped")
