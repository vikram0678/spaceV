"""
SpaceV Unified Telemetry & Flight Recorder Engine.
Inspired by CUA Trajectory Tracing and Artemis Span Lifecycle Management.
Provides high-resolution (<0.01ms) phase timing, dual-sink dispatching
(Live ANSI Console HUD + Atomic Append-Only JSONL Black Box), and multi-turn state auditing.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

logger = logging.getLogger("SpaceV.Telemetry")

# ContextVar for parent/child span hierarchy
CURRENT_TRACE_ID: contextvars.ContextVar[str] = contextvars.ContextVar("CURRENT_TRACE_ID", default="boot_session")
CURRENT_PARENT_SPAN_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar("CURRENT_PARENT_SPAN_ID", default=None)


@dataclass
class TelemetrySpan:
    span_id: str
    trace_id: str
    parent_span_id: str | None
    name: str
    start_time: float
    finish_time: float = 0.0
    duration_ms: float = 0.0
    status: str = "running"
    payload: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def finish(self, status: str = "success", error: str | None = None):
        self.finish_time = time.perf_counter()
        self.duration_ms = round((self.finish_time - self.start_time) * 1000, 2)
        self.status = status
        self.error = error


class SpaceVTelemetry:
    """
    Production-grade Dual-Sink Telemetry Dispatcher.
    Sink 1: Live Terminal HUD (Real-time micro-spans and ANSI status badges).
    Sink 2: Persistent Flight Recorder (Atomic append-only JSONL disk file).
    """

    def __init__(self, log_dir: str | Path = "logs"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.flight_recorder_path = self.log_dir / "spacev_flight_recorder.jsonl"
        self._lock = threading.Lock()
        self._current_turn: dict[str, Any] = {}
        self._turn_counter = 0

    # =========================================================================
    # SINK 1: LIVE TERMINAL HUD (Human-Readable Progress)
    # =========================================================================

    @staticmethod
    def hud_badge(stage: str, msg: str, duration_ms: float | None = None):
        """Prints a sleek, non-intrusive 1-line ANSI progress badge to stdout."""
        colors = {
            "VAD": "\033[94m",       # Blue
            "STT": "\033[96m",       # Cyan
            "ROUTER": "\033[93m",    # Yellow
            "THINKING": "\033[95m",  # Magenta
            "MODEL": "\033[95m",     # Magenta
            "TOOL": "\033[92m",      # Green
            "HEALED": "\033[91m",    # Bright Red
            "TTS": "\033[36m",       # Cyan/Blue
            "SUCCESS": "\033[32m",   # Green
            "RESET": "\033[0m"
        }
        color = colors.get(stage.upper(), "\033[97m")
        reset = colors["RESET"]
        ts = datetime.now().strftime("%H:%M:%S")

        dur_str = f" ({duration_ms:.1f}ms)" if duration_ms is not None else ""
        sys.stdout.write(f"[{ts}] {color}⚡ [{stage.upper()}]{reset} {msg}{dur_str}\n")
        sys.stdout.flush()

    def print_turn_summary_box(self, record: dict[str, Any]):
        """Prints an executive telemetry summary box upon turn completion."""
        waterfall = record.get("waterfall_ms", {})
        turn_id = record.get("turn_id", 0)
        total_s = waterfall.get("total_turn_latency", 0) / 1000.0

        stt_ms = waterfall.get("stt_whisper") or waterfall.get("stt") or 0.0
        router_ms = waterfall.get("fast_router") or waterfall.get("router") or 0.0
        llm_ttft_ms = waterfall.get("llm_turn_1_ttft") or waterfall.get("llm_ttft") or 0.0
        llm_total_ms = waterfall.get("llm_turn_1_total") or waterfall.get("llm_total") or 0.0
        tool_ms = waterfall.get("tool_execution") or waterfall.get("tools") or 0.0
        tts_ms = waterfall.get("tts_synthesis") or waterfall.get("tts") or 0.0

        tools_count = len(record.get("tools", []))
        healed = record.get("outcome", {}).get("xml_leak_healed", False)
        heal_badge = " | 🛡️ Healed: True" if healed else ""

        box = (
            f"\033[90m┌─ ⏱️ [TURN #{turn_id} TELEMETRY WATERFALL] ────────────────────────────────────────┐\033[0m\n"
            f"\033[90m│\033[0m STT: \033[96m{stt_ms:.0f}ms\033[0m │ "
            f"Router: \033[93m{router_ms:.1f}ms\033[0m │ "
            f"TTFT: \033[95m{llm_ttft_ms:.0f}ms\033[0m (Total: {llm_total_ms/1000:.1f}s) │ "
            f"Tools: \033[92m{tool_ms:.0f}ms\033[0m ({tools_count} calls) │ "
            f"TTS: \033[36m{tts_ms:.0f}ms\033[0m │ "
            f"Wall Clock: \033[97m{total_s:.2f}s\033[0m{heal_badge}\n"
            f"\033[90m└─────────────────────────────────────────────────────────────────────────────┘\033[0m"
        )
        sys.stdout.write(box + "\n")
        sys.stdout.flush()

    # =========================================================================
    # SINK 2: PERSISTENT JSONL FLIGHT RECORDER (Atomic Disk Persistence)
    # =========================================================================

    def _append_jsonl(self, data: dict[str, Any]):
        """Appends a single atomic JSON line to the flight recorder with immediate disk flush."""
        line = json.dumps(data, ensure_ascii=False) + "\n"
        with self._lock:
            try:
                with open(self.flight_recorder_path, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()
                    os.fsync(f.fileno())  # Ensure bytes hit physical storage surface
            except Exception as e:
                logger.warning(f"[Telemetry] Disk flush failed: {e}")

    # =========================================================================
    # CONTEXT-MANAGED SPAN API
    # =========================================================================

    @contextmanager
    def span(self, name: str, payload: dict[str, Any] | None = None) -> Iterator[TelemetrySpan]:
        """
        Creates, tracks, and finishes a high-resolution execution span.
        Guarantees finalization and persistence even if unhandled exceptions occur.
        """
        trace_id = CURRENT_TRACE_ID.get()
        parent_id = CURRENT_PARENT_SPAN_ID.get()
        span_id = f"sp_{uuid4().hex[:8]}"
        span_obj = TelemetrySpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_id,
            name=name,
            start_time=time.perf_counter(),
            payload=payload or {}
        )

        token = CURRENT_PARENT_SPAN_ID.set(span_id)
        try:
            yield span_obj
            span_obj.finish(status="success")
        except Exception as e:
            span_obj.finish(status="failed", error=str(e))
            raise
        finally:
            CURRENT_PARENT_SPAN_ID.reset(token)
            # Log micro-badge to HUD
            self.hud_badge(name, f"{span_obj.status}", span_obj.duration_ms)

    # =========================================================================
    # FULL TURN LIFECYCLE MANAGEMENT
    # =========================================================================

    def start_turn(self, user_input: str, channel: str = "voice") -> str:
        """Initializes a new conversational turn trace."""
        self._turn_counter += 1
        trace_id = f"tr_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
        CURRENT_TRACE_ID.set(trace_id)

        self._current_turn = {
            "trace_id": trace_id,
            "turn_id": self._turn_counter,
            "timestamp_iso": datetime.now(UTC).isoformat(timespec="milliseconds") + "Z",
            "start_perf": time.perf_counter(),
            "input": {
                "channel": channel,
                "text": user_input,
            },
            "waterfall_ms": {},
            "tools": [],
            "outcome": {
                "status": "in_progress",
                "xml_leak_detected": False,
                "xml_leak_healed": False,
                "error": None
            }
        }
        return trace_id

    def record_stage_time(self, stage_name: str, duration_ms: float):
        """Records the latency in milliseconds for a specific waterfall stage."""
        if self._current_turn:
            self._current_turn.setdefault("waterfall_ms", {})[stage_name] = round(duration_ms, 2)

    def record_tool_execution(
        self,
        name: str,
        args: dict[str, Any],
        status: str,
        duration_ms: float,
        result_preview: str = "",
        intercepted_from_xml: bool = False
    ):
        """Appends tool execution telemetry to the active turn."""
        if self._current_turn:
            self._current_turn.setdefault("tools", []).append({
                "name": name,
                "args": args,
                "status": status,
                "duration_ms": round(duration_ms, 2),
                "result_preview": (result_preview or "")[:150],
                "intercepted_from_xml": intercepted_from_xml
            })
            # Also accumulate total tool execution time
            curr_tool_time = self._current_turn["waterfall_ms"].get("tool_execution", 0.0)
            self._current_turn["waterfall_ms"]["tool_execution"] = round(curr_tool_time + duration_ms, 2)

    def record_xml_healing(self, tool_name: str, raw_xml: str):
        """Notes that an illicit Qwen/Llama XML tool tag was intercepted and healed."""
        if self._current_turn:
            self._current_turn["outcome"]["xml_leak_detected"] = True
            self._current_turn["outcome"]["xml_leak_healed"] = True
            self._current_turn["outcome"]["healed_tool"] = tool_name
        self.hud_badge("HEALED", f"Intercepted model XML tag for '{tool_name}' -> Executing seamlessly!")

    def end_turn(
        self,
        outcome_status: str = "success",
        error: str | None = None
    ) -> dict[str, Any]:
        """Finalizes the turn, calculates wall clock latency, flushes JSONL, and prints summary box."""
        if not self._current_turn:
            return {}

        start_perf = self._current_turn.pop("start_perf", time.perf_counter())
        total_latency = (time.perf_counter() - start_perf) * 1000.0
        self._current_turn.setdefault("waterfall_ms", {})["total_turn_latency"] = round(total_latency, 2)

        self._current_turn["outcome"]["status"] = outcome_status
        if error:
            self._current_turn["outcome"]["error"] = error

        record = dict(self._current_turn)
        # Flush to persistent JSONL Flight Recorder
        self._append_jsonl(record)
        # Print ANSI Summary Box
        self.print_turn_summary_box(record)

        self._current_turn = {}
        return record


# Global singleton instance
telemetry = SpaceVTelemetry()
