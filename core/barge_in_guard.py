"""
SpaceV Sub-150ms Instant Barge-In & Emergency Stop Coordinator.
Coordinates low-latency cancellation across actuator, LLM streaming,
and background execution threads.
Strictly abolishes regex matching, hardcoded delays, and static strings.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("SpaceV.BargeInGuard")


class HaltTriggerReason(str, Enum):
    """Categorical source origins for emergency halt events."""
    VOICE_BARGE_IN = "voice_barge_in"
    HARDWARE_HOTKEY = "hardware_hotkey"
    PHYSICAL_CORNER_FAILSAFE = "physical_corner_failsafe"
    USER_EXPLICIT_COMMAND = "user_explicit_command"
    CONTAINMENT_TRIPWIRE = "containment_tripwire"


@dataclass
class HaltTelemetryRecord:
    """Telemetry capturing an emergency stop occurrence."""
    timestamp: float
    trigger_reason: HaltTriggerReason
    elapsed_halt_us: float
    registered_handlers_invoked: int
    metadata: Dict[str, Any] = field(default_factory=dict)


class BargeInCoordinator:
    """
    Sub-150ms cancellation coordinator binding voice VAD, physical actuators,
    and agent execution state machines to an atomic emergency halt bus.
    """

    def __init__(self):
        self._halt_event = threading.Event()
        self._lock = threading.Lock()
        self._registered_handlers: List[Callable[[], None]] = []
        self._history: List[HaltTelemetryRecord] = []

    def is_halt_requested(self) -> bool:
        """Returns True if an emergency stop has been flagged."""
        return self._halt_event.is_set()

    def register_cancellation_handler(self, handler: Callable[[], None]) -> None:
        """Registers an asynchronous cancellation callback (e.g. aborting mouse/TTS/LLM)."""
        with self._lock:
            self._registered_handlers.append(handler)

    def trigger_emergency_stop(
        self,
        reason: HaltTriggerReason,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> HaltTelemetryRecord:
        """
        Executes immediate, high-priority halt across all registered actuators and runtimes.
        Measures flush latency in microseconds.
        """
        t0 = time.perf_counter()
        self._halt_event.set()

        invoked_count = 0
        with self._lock:
            for handler in self._registered_handlers:
                try:
                    handler()
                    invoked_count += 1
                except Exception as exc:
                    logger.debug("Cancellation handler encountered non-fatal error: %s", exc)

        t_elapsed = (time.perf_counter() - t0) * 1_000_000.0  # microseconds

        record = HaltTelemetryRecord(
            timestamp=time.time(),
            trigger_reason=reason,
            elapsed_halt_us=round(t_elapsed, 2),
            registered_handlers_invoked=invoked_count,
            metadata=metadata or {},
        )
        self._history.append(record)
        return record

    def reset(self) -> None:
        """Resets the emergency stop state to allow new tasks to begin."""
        self._halt_event.clear()

    @property
    def halt_history(self) -> List[HaltTelemetryRecord]:
        return list(self._history)


# Global singleton
barge_in_guard = BargeInCoordinator()
