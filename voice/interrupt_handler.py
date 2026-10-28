"""
SpaceV Full-Duplex Voice Interruption Protocol (Volume I §3 & Volume III §25).
Coordinates zero-latency barge-in handling:
  - Detects conversational turn-taking via Silero VAD + AEC Reference Guard
  - Purges downstream TTS audio playback buffers in microseconds (<200ms stop guarantee)
  - Signals active streaming LLM generation cancellation
  - Discards partial interrupted text to prevent conversation history contamination
  - Publishes 'voice.interrupt' events to SpaceV EventBus
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
import time
from typing import Any

from core.event_bus import EventPriority, event_bus
from voice.aec_guard import aec_guard

logger = logging.getLogger("SpaceV.InterruptHandler")


@dataclass
class InterruptionEvent:
    """Telemetry data capturing an interruption occurrence."""
    reason: str
    timestamp: float
    tts_halted: bool = True
    llm_cancelled: bool = True
    discarded_chars: int = 0
    discarded_tokens: int = 0
    flush_latency_us: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason": self.reason,
            "timestamp": self.timestamp,
            "tts_halted": self.tts_halted,
            "llm_cancelled": self.llm_cancelled,
            "discarded_chars": self.discarded_chars,
            "discarded_tokens": self.discarded_tokens,
            "flush_latency_us": self.flush_latency_us,
        }


class InterruptionProtocol:
    """
    Orchestrates full-duplex conversational barge-in across audio, VAD, LLM, and TTS pipelines.
    """

    def __init__(
        self,
        bus=None,
        pipeline=None,
        tts=None,
    ):
        self.event_bus = bus or event_bus
        self.pipeline = pipeline
        self.tts = tts
        self._llm_cancel_callbacks: list[Callable[[], None]] = []
        self._interruption_history: list[InterruptionEvent] = []
        self._is_interrupted: bool = False

        # Register with AEC Reference Guard
        aec_guard.register_barge_in_callback(self.trigger_barge_in)

    def register_llm_cancel_callback(self, callback: Callable[[], None]):
        """Registers a callback to abort ongoing token generation immediately."""
        self._llm_cancel_callbacks.append(callback)

    def trigger_barge_in(self, reason: str = "aec_barge_in"):
        """Invoked directly by AEC guard when high-energy speech is detected during speaker output."""
        return self.handle_interruption(reason=reason)

    def handle_interruption(
        self,
        reason: str = "user_barge_in",
        partial_response: str = ""
    ) -> InterruptionEvent:
        """
        Executes complete interruption sequence:
        1. Purges audio playback buffer.
        2. Cancels in-flight LLM streaming.
        3. Records discarded tokens (preventing context pollution).
        4. Emits CRITICAL event to EventBus.
        """
        t0 = time.perf_counter_ns()
        self._is_interrupted = True

        # 1. Flush frame pipeline
        flush_latency = 0.0
        pipe = self.pipeline
        if pipe is None:
            try:
                from voice.frame_pipeline import frame_pipeline
                pipe = frame_pipeline
            except Exception:
                pass

        if pipe and hasattr(pipe, "flush_microsecond"):
            try:
                res = pipe.flush_microsecond(reason=reason)
                flush_latency = res.get("duration_us", 0.0) if isinstance(res, dict) else 0.0
            except Exception as e:
                logger.debug(f"[INTERRUPT] Frame pipeline flush error: {e}")

        # 2. Halt TTS Engine
        tts_halted = False
        engine = self.tts
        if engine is None:
            try:
                from voice.tts_engine import tts_engine
                engine = tts_engine
            except Exception:
                pass

        if engine and hasattr(engine, "stop_speaking"):
            try:
                engine.stop_speaking()
                tts_halted = True
            except Exception as e:
                logger.debug(f"[INTERRUPT] TTS stop error: {e}")

        # 3. Abort LLM token generation
        llm_cancelled = False
        for cb in self._llm_cancel_callbacks:
            try:
                cb()
                llm_cancelled = True
            except Exception as e:
                logger.debug(f"[INTERRUPT] LLM cancel callback error: {e}")

        # 4. Compute discarded tokens
        discarded_chars = len(partial_response)
        discarded_tokens = max(0, discarded_chars // 4)

        duration_us = (time.perf_counter_ns() - t0) / 1000.0
        event = InterruptionEvent(
            reason=reason,
            timestamp=time.time(),
            tts_halted=tts_halted,
            llm_cancelled=llm_cancelled,
            discarded_chars=discarded_chars,
            discarded_tokens=discarded_tokens,
            flush_latency_us=round(duration_us if flush_latency == 0.0 else flush_latency, 2),
        )

        self._interruption_history.append(event)
        logger.info(
            f"[INTERRUPT] Full-duplex barge-in processed in {event.flush_latency_us} μs "
            f"(reason='{reason}', discarded ~{discarded_tokens} tokens)."
        )

        # 5. Publish to EventBus
        if self.event_bus:
            try:
                self.event_bus.publish(
                    topic="voice.interrupt",
                    payload=event.to_dict(),
                    priority=EventPriority.CRITICAL,
                    source="voice.interrupt_handler"
                )
            except Exception as e:
                logger.debug(f"[INTERRUPT] EventBus publish error: {e}")

        return event

    def reset(self):
        """Resets the interruption flag for the next turn."""
        self._is_interrupted = False

    @property
    def is_interrupted(self) -> bool:
        return self._is_interrupted

    def get_history(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._interruption_history]


# Global singleton instance
interruption_protocol = InterruptionProtocol()
