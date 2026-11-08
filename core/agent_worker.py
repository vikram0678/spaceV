"""
Background Worker Thread with Real-Time Word Streaming, 0ms Fast-Path Dispatcher,
and Pipecat-style Speculative Turn-Taking Gate.
"""
import threading
from enum import Enum

from PyQt6.QtCore import QThread, pyqtSignal

from core.graph_engine import SpaceVGraphEngine
from core.ollama_client import OllamaAgent
from voice.tts_engine import tts




class SpeculationState(Enum):
    OPEN = "open"
    HOLDING = "holding"
    DROPPING = "dropping"


class SpeculationGate:
    """
    Decides when speculative LLM tokens and audio output are emitted or discarded.
    Inspired by Pipecat AI (eto/pipecat/src/pipecat/turns/speculation_gate.py).
    Holds provisional bot responses during speech pauses until turn finality is confirmed.
    """

    def __init__(self, is_speculative: bool = False, name: str = "SpeculationGate"):
        self.name = name
        self._state = SpeculationState.HOLDING if is_speculative else SpeculationState.OPEN
        self._held_tokens: list[str] = []
        self._lock = threading.Lock()

    @property
    def state(self) -> SpeculationState:
        return self._state

    @property
    def is_holding(self) -> bool:
        return self._state == SpeculationState.HOLDING

    @property
    def is_speculating(self) -> bool:
        return self._state == SpeculationState.HOLDING

    def hold_token(self, token: str) -> None:
        with self._lock:
            if self._state == SpeculationState.HOLDING:
                self._held_tokens.append(token)

    def confirm(self) -> list[str]:
        with self._lock:
            self._state = SpeculationState.OPEN
            tokens = list(self._held_tokens)
            self._held_tokens.clear()
            return tokens

    def cancel(self) -> None:
        with self._lock:
            self._state = SpeculationState.DROPPING
            self._held_tokens.clear()


class AgentWorker(QThread):
    started_processing = pyqtSignal()
    token_received = pyqtSignal(str)          # Live streamed tokens
    tool_event = pyqtSignal(str, str, str)    # (tool_name, status, details)
    response_ready = pyqtSignal(str)          # Final complete response
    error_occurred = pyqtSignal(str)

    def __init__(self, agent: OllamaAgent, user_prompt: str, is_speculative: bool = False):
        super().__init__()
        self.agent = agent
        self.user_prompt = user_prompt
        self.graph_engine = SpaceVGraphEngine(agent=self.agent)
        self._is_aborted = False
        self.speculation_gate = SpeculationGate(is_speculative=is_speculative)
        self._speculation_lock = threading.Lock()
        self._pending_response: str | None = None
        self._streamer = None

    def abort(self):
        """Immediately halts active inference and streaming upon conversational interruption."""
        self._is_aborted = True
        tts.stop()

    def confirm_speculation(self):
        """Releases held tokens from speculative inference into the live UI and TTS stream."""
        with self._speculation_lock:
            tokens = self.speculation_gate.confirm()
            for t in tokens:
                self.token_received.emit(t)
                if self._streamer:
                    self._streamer.feed(t)

            if self._pending_response is not None and not self._is_aborted:
                resp = self._pending_response
                self._pending_response = None
                self.response_ready.emit(resp)
                if self._streamer and self._streamer.has_streamed:
                    self._streamer.flush()
                elif tts.is_enabled and resp and not self._is_aborted:
                    tts.speak(resp)

    def cancel_speculation(self):
        """Discards speculative inference without emitting tokens or speaking."""
        with self._speculation_lock:
            self.speculation_gate.cancel()
        self.abort()

    def run(self):
        self.started_processing.emit()

        streamer = tts.create_sentence_streamer() if tts.is_enabled else None
        self._streamer = streamer

        def tool_callback(name, args, status_or_result):
            if self._is_aborted:
                return
            if status_or_result == "running":
                self.tool_event.emit(name, "running", str(args))
            else:
                self.tool_event.emit(name, "completed", str(status_or_result))

        def token_callback(token: str):
            if self._is_aborted:
                return
            with self._speculation_lock:
                if self.speculation_gate.is_holding:
                    self.speculation_gate.hold_token(token)
                    return
            self.token_received.emit(token)
            if streamer:
                streamer.feed(token)

        try:
            response = self.graph_engine.run(
                self.user_prompt,
                tool_callback=tool_callback,
                token_callback=token_callback
            )
            if self._is_aborted:
                return

            with self._speculation_lock:
                if self.speculation_gate.is_holding:
                    self._pending_response = response
                    return

            self.response_ready.emit(response)

            # Finalize streaming audio
            if streamer and streamer.has_streamed:
                streamer.flush()
            elif tts.is_enabled and response and not self._is_aborted:
                # For non-streamed responses (e.g. fast router matches)
                tts.speak(response)
        except Exception as e:
            if not self._is_aborted:
                if streamer:
                    streamer.flush()
                self.error_occurred.emit(str(e))


