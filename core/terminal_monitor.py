"""
SpaceV Ambient Terminal Output Monitor (Volume I §4.5 & Volume III §24).
Observes active terminal, PTY, and CLI tool streams for:
  - Python tracebacks, SyntaxErrors, and ModuleNotFoundErrors
  - Build errors (npm ERR, cargo panic, make error)
  - Test outcomes (pytest failures / passes)
  - Long-running command completions
Emits structured TerminalEvent objects for automatic agent self-healing.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import re
import time

logger = logging.getLogger("SpaceV.TerminalMonitor")


@dataclass
class TerminalEvent:
    """Structured event emitted when an active terminal line matches a monitored pattern."""
    event_type: str          # "python_traceback" | "test_failure" | "build_failure" | "test_passed" | etc.
    terminal_id: str         # Session identifier
    matched_pattern: str     # Regex pattern that fired
    matched_text: str        # The raw line
    context_lines: list[str] # Preceding lines for root-cause context
    timestamp: float
    severity: str = "info"   # "info" | "warning" | "error" | "critical"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "terminal_id": self.terminal_id,
            "matched_pattern": self.matched_pattern,
            "matched_text": self.matched_text,
            "context_lines": self.context_lines,
            "timestamp": self.timestamp,
            "severity": self.severity,
        }


# High-precision pattern matrix
ERROR_PATTERNS: list[tuple[re.Pattern, str, str]] = [
    (re.compile(r"Traceback \(most recent call last\):", re.IGNORECASE), "python_traceback", "error"),
    (re.compile(r"^SyntaxError:", re.IGNORECASE), "syntax_error", "error"),
    (re.compile(r"^ModuleNotFoundError:", re.IGNORECASE), "import_error", "error"),
    (re.compile(r"^PermissionError:", re.IGNORECASE), "permission_error", "error"),
    (re.compile(r"^ConnectionRefusedError:", re.IGNORECASE), "connection_error", "warning"),
    (re.compile(r"===+ FAILURES ===+|\bFAILED\b", re.IGNORECASE), "test_failure", "error"),
    (re.compile(r"\b\d+ failed\b", re.IGNORECASE), "test_failure", "error"),
    (re.compile(r"\b\d+ passed\b", re.IGNORECASE), "test_passed", "info"),
    (re.compile(r"npm ERR!", re.IGNORECASE), "npm_error", "error"),
    (re.compile(r"Build failed|Compilation failed", re.IGNORECASE), "build_failure", "critical"),
    (re.compile(r"Build successful|Compiled successfully", re.IGNORECASE), "build_success", "info"),
    (re.compile(r"\bError:\s+.+", re.IGNORECASE), "generic_error", "error"),
]


class SpaceVTerminalMonitor:
    """
    Read-only stream observer for shell and terminal buffers.
    Maintains a rolling ring buffer of recent lines per terminal and scans for actionable patterns.
    """

    def __init__(
        self,
        on_event: Callable[[TerminalEvent], None] | None = None,
        buffer_size: int = 50
    ):
        self.on_event = on_event
        self.buffer_size = buffer_size
        self._buffers: dict[str, list[str]] = {}
        self._events_detected: list[TerminalEvent] = []

    def process_line(
        self,
        terminal_id: str,
        line: str,
        timestamp: float | None = None
    ) -> TerminalEvent | None:
        """
        Processes a single terminal output line against the pattern matrix.
        Returns the TerminalEvent if a pattern matched, or None.
        """
        ts = timestamp or time.time()
        line_clean = line.rstrip("\r\n")

        # Update circular buffer
        if terminal_id not in self._buffers:
            self._buffers[terminal_id] = []
        buf = self._buffers[terminal_id]
        buf.append(line_clean)
        if len(buf) > self.buffer_size:
            buf.pop(0)

        # Match against patterns
        for pattern, event_type, severity in ERROR_PATTERNS:
            if pattern.search(line_clean):
                context_start = max(0, len(buf) - 6)
                context = list(buf[context_start:])

                event = TerminalEvent(
                    event_type=event_type,
                    terminal_id=terminal_id,
                    matched_pattern=pattern.pattern,
                    matched_text=line_clean.strip(),
                    context_lines=context,
                    timestamp=ts,
                    severity=severity,
                )
                self._events_detected.append(event)
                logger.debug(f"[TERMINAL_MONITOR] {event_type} in {terminal_id}: {line_clean[:80]}")

                if self.on_event:
                    try:
                        self.on_event(event)
                    except Exception as e:
                        logger.error(f"[TERMINAL_MONITOR] Event callback error: {e}")

                return event

        return None

    def process_chunk(self, terminal_id: str, chunk: str) -> list[TerminalEvent]:
        """Processes a multi-line output chunk."""
        events: list[TerminalEvent] = []
        for line in chunk.splitlines():
            ev = self.process_line(terminal_id, line)
            if ev:
                events.append(ev)
        return events

    def get_buffer(self, terminal_id: str) -> list[str]:
        return list(self._buffers.get(terminal_id, []))

    def clear_buffer(self, terminal_id: str):
        if terminal_id in self._buffers:
            self._buffers[terminal_id].clear()

    def get_events(self) -> list[TerminalEvent]:
        return list(self._events_detected)


# Global singleton instance
terminal_monitor = SpaceVTerminalMonitor()
