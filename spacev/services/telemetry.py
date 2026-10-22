"""
SpaceV Services Subsystem: Event-Driven Workflow Telemetry Engine.
Engineered from Langflow / LFX event propagation for real-time cybernetic monitoring.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WorkflowEvent:
    event_type: str  # 'node_start', 'node_finish', 'tool_call', 'error', 'barge_in'
    node_id: str
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    duration_ms: Optional[float] = None


class WorkflowTelemetry:
    """
    Captures node-level telemetry and emits real-time events to listeners (HUD, SSE, Loggers).
    """

    def __init__(self):
        self._listeners: List[Callable[[WorkflowEvent], None]] = []
        self._active_timers: Dict[str, float] = {}
        self.history: List[WorkflowEvent] = []

    def subscribe(self, listener: Callable[[WorkflowEvent], None]) -> None:
        self._listeners.append(listener)

    def _emit(self, event: WorkflowEvent) -> None:
        self.history.append(event)
        for listener in self._listeners:
            try:
                listener(event)
            except Exception:
                pass  # Telemetry emission never breaks core execution

    def start_node(self, node_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        self._active_timers[node_id] = time.perf_counter()
        self._emit(WorkflowEvent("node_start", node_id, metadata=metadata or {}))

    def finish_node(self, node_id: str, metadata: Optional[Dict[str, Any]] = None) -> float:
        start = self._active_timers.pop(node_id, None)
        duration_ms = (time.perf_counter() - start) * 1000.0 if start else 0.0
        self._emit(WorkflowEvent("node_finish", node_id, metadata=metadata or {}, duration_ms=duration_ms))
        return duration_ms

    def record_tool_call(self, tool_name: str, args: Dict[str, Any], duration_ms: float, success: bool) -> None:
        self._emit(
            WorkflowEvent(
                "tool_call",
                node_id=tool_name,
                metadata={"args": args, "success": success},
                duration_ms=duration_ms,
            )
        )

    def record_error(self, node_id: str, error_msg: str) -> None:
        self._emit(WorkflowEvent("error", node_id, metadata={"error": error_msg}))
