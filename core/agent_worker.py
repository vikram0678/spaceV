"""
Background Worker Thread with Real-Time Word Streaming & 0ms Fast-Path Dispatcher.
"""
from PyQt6.QtCore import QThread, pyqtSignal

from core.graph_engine import SpaceVGraphEngine
from core.ollama_client import OllamaAgent
from voice.tts_engine import tts


class AgentWorker(QThread):
    started_processing = pyqtSignal()
    token_received = pyqtSignal(str)          # Live streamed tokens
    tool_event = pyqtSignal(str, str, str)    # (tool_name, status, details)
    response_ready = pyqtSignal(str)          # Final complete response
    error_occurred = pyqtSignal(str)

    def __init__(self, agent: OllamaAgent, user_prompt: str):
        super().__init__()
        self.agent = agent
        self.user_prompt = user_prompt
        self.graph_engine = SpaceVGraphEngine(agent=self.agent)
        self._is_aborted = False

    def abort(self):
        """Immediately halts active inference and streaming upon conversational interruption."""
        self._is_aborted = True
        tts.stop()

    def run(self):
        self.started_processing.emit()

        streamer = tts.create_sentence_streamer() if tts.is_enabled else None

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

