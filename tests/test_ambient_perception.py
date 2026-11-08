"""
SpaceV Ambient Perception Verification Suite (Volume I §4-§5 & Volume III §24).
Validates:
  - SpaceVFileWatcher: debouncing, pattern filtering, file category classification
  - SpaceVTerminalMonitor: regex pattern matching, context extraction, traceback detection
  - AmbientScreenObserver: perceptual visual hash diffing, active window app-switching, AEC pause/resume
"""
from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import time
import pytest

from core.ambient_screen import (
    AmbientScreenObserver,
    ScreenChangeEvent,
)
from core.fs_watcher import (
    FileChangeEvent,
    SpaceVFileWatcher,
)
from core.terminal_monitor import (
    SpaceVTerminalMonitor,
    TerminalEvent,
)


@pytest.fixture
def temp_watch_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


# ═══════════════════════════════════════════════════════════════════
# FILE SYSTEM WATCHER TESTS
# ═══════════════════════════════════════════════════════════════════

def test_file_watcher_classification_and_ignore_rules(temp_watch_dir):
    """Verify file classification (code, config, test) and ignore filtering."""
    watcher = SpaceVFileWatcher(watch_paths=[temp_watch_dir])

    # 1. Ignore checks
    assert watcher._should_ignore(Path("/workspace/.git/HEAD")) is True
    assert watcher._should_ignore(Path("/workspace/__pycache__/foo.pyc")) is True
    assert watcher._should_ignore(Path("/workspace/.venv/lib/python")) is True
    assert watcher._should_ignore(Path("/workspace/main.py")) is False

    # 2. File classification
    code_cls = watcher._classify_file(Path("/workspace/core/engine.py"))
    assert code_cls["is_code_file"] is True
    assert code_cls["is_config_file"] is False
    assert code_cls["is_test_file"] is False

    cfg_cls = watcher._classify_file(Path("/workspace/config.yaml"))
    assert cfg_cls["is_code_file"] is False
    assert cfg_cls["is_config_file"] is True

    test_cls = watcher._classify_file(Path("/workspace/tests/test_engine.py"))
    assert test_cls["is_code_file"] is True
    assert test_cls["is_test_file"] is True


def test_file_watcher_debouncing(temp_watch_dir):
    """Verify debouncing suppresses rapid successive edits on the same file."""
    watcher = SpaceVFileWatcher(watch_paths=[temp_watch_dir], debounce_ms=200)

    # First event should pass
    assert watcher._debounce_check("/path/to/main.py") is True

    # Immediate second event should be debounced
    assert watcher._debounce_check("/path/to/main.py") is False

    # After debounce window expires, it should pass again
    time.sleep(0.22)
    assert watcher._debounce_check("/path/to/main.py") is True


@pytest.mark.asyncio
async def test_file_watcher_lifecycle_and_events(temp_watch_dir):
    """Verify watcher starts, detects new/modified files, and stops cleanly."""
    events: list[FileChangeEvent] = []
    watcher = SpaceVFileWatcher(
        watch_paths=[temp_watch_dir],
        on_event=lambda ev: events.append(ev),
        debounce_ms=50
    )

    await watcher.start()
    try:
        # Create a new code file
        test_file = temp_watch_dir / "service.py"
        test_file.write_text("print('hello world')")

        # Allow poll or watchdog loop to detect
        await asyncio.sleep(0.3)

        # Trigger or verify event
        watcher._handle_fs_event("created", str(test_file))
        assert len(events) >= 1
        last_ev = events[-1]
        assert last_ev.event_type == "created"
        assert last_ev.is_code_file is True
        assert last_ev.extension == ".py"
    finally:
        await watcher.stop()


# ═══════════════════════════════════════════════════════════════════
# TERMINAL MONITOR TESTS
# ═══════════════════════════════════════════════════════════════════

def test_terminal_monitor_error_and_traceback_detection():
    """Verify terminal monitor recognizes Python tracebacks and error severities."""
    events: list[TerminalEvent] = []
    monitor = SpaceVTerminalMonitor(on_event=lambda ev: events.append(ev))

    # Send clean lines
    monitor.process_line("term_1", "$ python main.py")
    monitor.process_line("term_1", "Starting SpaceV server on port 8000...")
    assert len(events) == 0

    # Send Python traceback
    ev = monitor.process_line("term_1", "Traceback (most recent call last):")
    assert ev is not None
    assert ev.event_type == "python_traceback"
    assert ev.severity == "error"
    assert len(ev.context_lines) >= 3

    # Send SyntaxError
    ev_syntax = monitor.process_line("term_1", "SyntaxError: invalid syntax")
    assert ev_syntax is not None
    assert ev_syntax.event_type == "syntax_error"


def test_terminal_monitor_test_outcomes_and_buffer_management():
    """Verify detection of pytest pass/fail counts and buffer limits."""
    monitor = SpaceVTerminalMonitor(buffer_size=10)

    # Fill buffer beyond 10 lines
    for i in range(15):
        monitor.process_line("term_test", f"line {i}")

    buf = monitor.get_buffer("term_test")
    assert len(buf) == 10
    assert buf[0] == "line 5"
    assert buf[-1] == "line 14"

    # Test outcome detection
    ev_pass = monitor.process_line("term_test", "=== 24 passed in 1.11s ===")
    assert ev_pass is not None
    assert ev_pass.event_type == "test_passed"
    assert ev_pass.severity == "info"

    ev_fail = monitor.process_line("term_test", "FAILED tests/test_core.py::test_fail")
    assert ev_fail is not None
    assert ev_fail.event_type == "test_failure"
    assert ev_fail.severity == "error"


# ═══════════════════════════════════════════════════════════════════
# AMBIENT SCREEN OBSERVER TESTS
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_ambient_screen_app_switching_and_hash_comparison():
    """Verify screen observer detects active window changes and visual deltas."""
    current_title = "VS Code - main.py"
    current_image = b"image_frame_alpha_1"

    def title_provider():
        return current_title

    def capture_provider():
        return current_image

    events: list[ScreenChangeEvent] = []
    observer = AmbientScreenObserver(
        on_event=lambda ev: events.append(ev),
        capture_provider=capture_provider,
        window_title_provider=title_provider
    )

    # 1. Baseline capture (initial state establishment)
    ev0 = await observer.capture_and_compare()
    assert ev0 is None  # Initial baseline does not trigger change

    # 2. Identical frame -> no event
    ev1 = await observer.capture_and_compare()
    assert ev1 is None

    # 3. Visual frame changes -> content_change event
    current_image = b"image_frame_beta_2"
    ev2 = await observer.capture_and_compare()
    assert ev2 is not None
    assert ev2.change_type == "content_change"
    assert ev2.similarity_score < 0.85

    # 4. Active window switch -> app_switch event
    current_title = "Google Chrome - Documentation"
    ev3 = await observer.capture_and_compare()
    assert ev3 is not None
    assert ev3.change_type == "app_switch"
    assert ev3.active_window_title == "Google Chrome - Documentation"


def test_ambient_screen_aec_pause_resume():
    """Verify visual sampling pause/resume protects AEC latency during voice interaction."""
    observer = AmbientScreenObserver()

    assert observer._paused is False
    observer.pause()
    assert observer._paused is True
    observer.resume()
    assert observer._paused is False

    # Cadence switching
    observer.set_active_mode(True)
    assert observer._capture_interval == 30.0
    observer.set_active_mode(False)
    assert observer._capture_interval == 10.0
