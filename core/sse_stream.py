"""
SpaceV Server-Sent Events (SSE) Streaming & Real-Time Token Bridge (Upgrade #48).
Provides zero-latency word-by-word streaming to local chat UIs, web dashboards,
and remote companion endpoints using standard W3C Server-Sent Events protocol.
"""
from __future__ import annotations

import json
import time
import queue
import logging
from typing import Dict, Any, Optional, Generator, AsyncGenerator
from dataclasses import dataclass

logger = logging.getLogger("SpaceV.SSE")


@dataclass
class SSEMessage:
    event: str
    data: Dict[str, Any]
    id: Optional[str] = None

    def encode(self) -> str:
        """Encodes event into standard W3C text/event-stream wire format."""
        lines = []
        if self.id:
            lines.append(f"id: {self.id}")
        lines.append(f"event: {self.event}")
        payload_str = json.dumps(self.data, separators=(',', ':'))
        lines.append(f"data: {payload_str}")
        return "\n".join(lines) + "\n\n"


class SSEBroadcaster:
    """
    Thread-safe pub/sub hub for live token streaming, reflex triggers, and HUD events.
    """
    def __init__(self):
        self._subscribers: List[queue.Queue] = []

    def subscribe(self, max_buffer: int = 100) -> queue.Queue:
        """Subscribes an active client stream queue."""
        q: queue.Queue = queue.Queue(maxsize=max_buffer)
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue):
        """Unsubscribes a disconnected client queue."""
        if q in self._subscribers:
            self._subscribers.remove(q)

    def publish(self, event: str, data: Dict[str, Any], event_id: Optional[str] = None):
        """Broadcasts an event message to all connected clients."""
        msg = SSEMessage(event=event, data=data, id=event_id)
        encoded = msg.encode()

        stale = []
        for q in self._subscribers:
            try:
                q.put_nowait(encoded)
            except queue.Full:
                stale.append(q)
        for s in stale:
            self.unsubscribe(s)

    def emit_token(self, token: str):
        """Streams an incremental LLM token."""
        self.publish("token", {"token": token, "ts": time.time()})

    def emit_draft(self, draft_text: str):
        """Streams a real-time STT speech draft."""
        self.publish("draft", {"text": draft_text, "ts": time.time()})

    def emit_reflex(self, tool_name: str, args: Dict[str, Any], latency_ms: float):
        """Broadcasts a sub-0.5ms deterministic reflex match."""
        self.publish("reflex", {
            "tool": tool_name,
            "args": args,
            "latency_ms": latency_ms,
            "ts": time.time()
        })

    def emit_telemetry(self, cpu_pct: float, ram_pct: float, state: str):
        """Broadcasts a system telemetry update."""
        self.publish("telemetry", {
            "cpu_percent": cpu_pct,
            "ram_percent": ram_pct,
            "companion_state": state,
            "ts": time.time()
        })

    def emit_done(self, final_text: str = ""):
        """Signals conversational turn completion."""
        self.publish("done", {"final_text": final_text, "ts": time.time()})


sse_broadcaster = SSEBroadcaster()
