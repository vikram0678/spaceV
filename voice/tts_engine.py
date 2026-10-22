"""
Offline Voice Text-to-Speech Engine for SpaceV.
Powered by native Windows SAPI5 (win32com) with pyttsx3 fallback.
Runs on a dedicated QThread with thread-safe Qt signal emission, eliminating
cross-thread QWidget painting collisions and segmentation faults.
Features low-latency sentence-by-sentence streaming for instant response.
"""
import os
import sys
import queue
import re
import time
import io
import asyncio
from typing import Optional, Callable
from PyQt6.QtCore import QThread, pyqtSignal
from config import USE_NEURAL_TTS, TTS_NEURAL_VOICE

# In WSL2/WSLg, route SDL audio directly to the PulseAudio bridge
if sys.platform != "win32" and os.path.exists("/mnt/wslg/PulseServer"):
    os.environ.setdefault("SDL_AUDIODRIVER", "pulseaudio")

try:
    import edge_tts
    HAS_EDGE_TTS = True
except ImportError:
    HAS_EDGE_TTS = False

try:
    import pygame
    HAS_PYGAME = True
except ImportError:
    HAS_PYGAME = False


class VoiceProsodyEngine:
    """
    Dynamic Emotional Prosody and Cadence Modulation Engine (Upgrade #7).
    Adjusts pitch, rate, and pacing to match conversational mood and urgency.
    """
    PROFILES = {
        "affirmative": {"rate": "+6%", "pitch": "+2Hz", "sapi_rate": 2},
        "analytical": {"rate": "-4%", "pitch": "+0Hz", "sapi_rate": 0},
        "alert": {"rate": "+8%", "pitch": "+4Hz", "sapi_rate": 3},
        "conversational": {"rate": "+0%", "pitch": "+0Hz", "sapi_rate": 1},
    }

    @classmethod
    def detect_profile(cls, text: str) -> str:
        clean = text.lower().strip()
        if any(w in clean for w in ["warning", "alert", "threat", "danger", "security", "denied", "⚠️"]):
            return "alert"
        if any(clean.startswith(w) for w in ["right away", "searching", "initializing", "opening", "launching", "playing"]):
            return "affirmative"
        if any(w in clean for w in ["def ", "class ", "return ", "algorithm", "telemetry", "metric", "analysis", "system"]):
            return "analytical"
        return "conversational"


class SentenceStreamBuffer:
    """
    Buffers incoming tokens from LLM streaming and yields complete sentences
    the moment terminal punctuation is reached, enabling zero-latency voice playback.
    """
    def __init__(self, on_sentence_ready: Callable[[str], None], on_stream_finished: Optional[Callable[[], None]] = None):
        self.on_sentence_ready = on_sentence_ready
        self.on_stream_finished = on_stream_finished
        self.buffer = ""
        # Regex for sentence terminators followed by whitespace, newline, or end-of-string
        self.splitter = re.compile(r'([.!?]+(?:\s+|\n+|$))')
        self.has_streamed = False

    def feed(self, token: str):
        if not token:
            return
        self.buffer += token
        parts = self.splitter.split(self.buffer)
        if len(parts) > 2:
            # We have at least one complete sentence
            for i in range(0, len(parts) - 1, 2):
                sent = (parts[i] + parts[i+1]).strip()
                if sent:
                    self.has_streamed = True
                    self.on_sentence_ready(sent)
            self.buffer = parts[-1]
        elif len(self.buffer.split()) >= 14 and any(p in self.buffer for p in [', ', '; ', ': ', '—', ' - ']):
            # If buffer reaches 14+ words, yield clause early so audio starts without waiting for a long sentence
            for clause_delim in [', ', '; ', ': ', '—', ' - ']:
                if clause_delim in self.buffer:
                    idx = self.buffer.find(clause_delim) + len(clause_delim)
                    clause = self.buffer[:idx].strip()
                    self.buffer = self.buffer[idx:]
                    if clause:
                        self.has_streamed = True
                        self.on_sentence_ready(clause)
                    break

    def flush(self):
        remainder = self.buffer.strip()
        self.buffer = ""
        if remainder:
            self.has_streamed = True
            self.on_sentence_ready(remainder)
        if self.on_stream_finished:
            self.on_stream_finished()


# In-Memory 0ms High-Fidelity Neural Voice Cache
_NEURAL_AUDIO_CACHE: dict = {}


class TTSEngine(QThread):
    _instance: Optional["TTSEngine"] = None

    speech_started = pyqtSignal()
    speech_finished = pyqtSignal()

    def __init__(self):
        super().__init__()
        TTSEngine._instance = self
        self._queue = queue.Queue()
        self._is_enabled = True
        self._is_speaking = False
        self._is_running = True
        self._spk = None
        self._session_active = False
        self._stream_closed = False

        if HAS_PYGAME:
            try:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(frequency=44100, size=-16, channels=2)
                pygame.mixer.music.set_volume(1.0)
            except Exception as e:
                print(f"[TTS] Pygame mixer init note: {e}")

        # Backwards-compatible callback hooks
        self._on_started_hook = None
        self._on_finished_hook = None

        try:
            from voice.aec_guard import aec_guard
            aec_guard.register_barge_in_callback(self.stop)
        except Exception:
            pass

        self.start()

    @property
    def on_speech_started(self):
        return self._on_started_hook

    @on_speech_started.setter
    def on_speech_started(self, callback):
        self._on_started_hook = callback
        if callable(callback):
            try:
                self.speech_started.connect(callback)
            except Exception:
                pass

    @property
    def on_speech_finished(self):
        return self._on_finished_hook

    @on_speech_finished.setter
    def on_speech_finished(self, callback):
        self._on_finished_hook = callback
        if callable(callback):
            try:
                self.speech_finished.connect(callback)
            except Exception:
                pass

    @property
    def is_enabled(self) -> bool:
        return self._is_enabled

    @is_enabled.setter
    def is_enabled(self, value: bool):
        self._is_enabled = value
        if not value:
            self.stop()

    @property
    def is_speaking(self) -> bool:
        return self._is_speaking

    @staticmethod
    def clean_text_for_speech(text: str) -> str:
        """Strips markdown code blocks, URLs, and formatting characters for crisp, natural voice delivery."""
        if not text:
            return ""
        # Remove markdown code blocks completely (don't read raw code aloud)
        clean = re.sub(r'```.*?```', ' code snippet omitted ', text, flags=re.DOTALL)
        clean = re.sub(r'`[^`]+`', ' ', clean)
        # Remove URLs
        clean = re.sub(r'https?://\S+', '', clean)
        # Remove markdown formatting characters
        clean = re.sub(r'[*_#~>•\[\]()]', ' ', clean)
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean

    def run(self):
        """Dedicated QThread event loop with platform-aware speech synthesis."""
        # 1. Native Windows SAPI SpVoice (Win32 COM) - Windows only
        if sys.platform == "win32":
            try:
                import pythoncom
                import win32com.client
                pythoncom.CoInitialize()
                self._spk = win32com.client.Dispatch("SAPI.SpVoice")
                self._spk.Rate = 1       # Natural pacing (+1 is energetic and crisp)
                self._spk.Volume = 100   # Clear volume

                # Select preferred lady voice (Zira for offline, Aria for Neural)
                try:
                    for v in self._spk.GetVoices():
                        desc = v.GetDescription().lower()
                        if "zira" in desc or "female" in desc or "eva" in desc:
                            self._spk.Voice = v
                            break
                except Exception:
                    pass
            except Exception:
                self._spk = None
        else:
            self._spk = None

        # 2. Universal offline fallback engine (pyttsx3 / espeak on Linux, NSSpeech on macOS)
        engine = None
        if self._spk is None:
            try:
                import pyttsx3
                engine = pyttsx3.init()
                engine.setProperty('rate', 185)
                engine.setProperty('volume', 1.0)
            except Exception:
                engine = None

        while self._is_running:
            try:
                msg = self._queue.get(timeout=0.1)
            except queue.Empty:
                # If queue is empty and stream was closed, end speech session cleanly
                if self._session_active and self._stream_closed and not self._is_speaking:
                    self._session_active = False
                    self._stream_closed = False
                    self.speech_finished.emit()
                continue

            if msg is None:
                break

            action, text = msg

            if action == "finish_stream":
                self._stream_closed = True
                if self._queue.empty() and not self._is_speaking:
                    self._session_active = False
                    self._stream_closed = False
                    self.speech_finished.emit()
                self._queue.task_done()
                continue

            if not self._is_enabled or not text or not text.strip():
                self._queue.task_done()
                continue

            clean = self.clean_text_for_speech(text)
            if not clean:
                self._queue.task_done()
                continue

            # Start of speaking session
            if not self._session_active:
                self._session_active = True
                self.speech_started.emit()

            self._is_speaking = True
            try:
                from voice.aec_guard import aec_guard
                aec_guard.set_speaker_active(True)
            except Exception:
                pass

            # Detect dynamic emotional prosody profile (Upgrade #7)
            profile_name = VoiceProsodyEngine.detect_profile(clean)
            prosody = VoiceProsodyEngine.PROFILES.get(profile_name, VoiceProsodyEngine.PROFILES["conversational"])
            print(f"[TTS] 🔊 Speaking ({profile_name}): '{clean[:60]}...'")

            # 1. High-fidelity Microsoft Azure Neural Voice (Edge-TTS) with 0ms Audio Caching
            played_neural = False
            if USE_NEURAL_TTS and HAS_EDGE_TTS and HAS_PYGAME:
                try:
                    if not pygame.mixer.get_init():
                        try:
                            pygame.mixer.init(frequency=44100, size=-16, channels=2)
                        except Exception:
                            if "SDL_AUDIODRIVER" in os.environ:
                                del os.environ["SDL_AUDIODRIVER"]
                            try:
                                pygame.mixer.init(frequency=44100, size=-16, channels=2)
                            except Exception:
                                pass
                    if pygame.mixer.get_init():
                        pygame.mixer.music.set_volume(1.0)
                    cache_key = f"{profile_name}:{clean.lower().strip()}"
                    if cache_key in _NEURAL_AUDIO_CACHE and self._is_speaking and self._is_running:
                        audio_bytes = _NEURAL_AUDIO_CACHE[cache_key]
                        bio = io.BytesIO(audio_bytes)
                        pygame.mixer.music.load(bio)
                        pygame.mixer.music.play()
                        while pygame.mixer.music.get_busy() and self._is_speaking and self._is_running:
                            time.sleep(0.025)
                        played_neural = True
                    else:
                        rate_str = str(prosody.get("rate", "+0%")).strip()
                        if rate_str and not rate_str.startswith(("+", "-")):
                            rate_str = f"+{rate_str}"
                        pitch_str = str(prosody.get("pitch", "+0Hz")).strip()
                        if pitch_str and not pitch_str.startswith(("+", "-")):
                            pitch_str = f"+{pitch_str}"

                        communicate = edge_tts.Communicate(
                            clean,
                            voice=TTS_NEURAL_VOICE,
                            rate=rate_str,
                            pitch=pitch_str
                        )
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)

                        async def _collect_audio():
                            data = b""
                            async for chunk in communicate.stream():
                                if chunk["type"] == "audio":
                                    data += chunk["data"]
                            return data

                        audio_bytes = loop.run_until_complete(_collect_audio())
                        loop.close()

                        if audio_bytes and self._is_speaking and self._is_running:
                            if len(audio_bytes) <= 600_000:
                                _NEURAL_AUDIO_CACHE[cache_key] = audio_bytes
                            bio = io.BytesIO(audio_bytes)
                            pygame.mixer.music.load(bio)
                            pygame.mixer.music.play()
                            while pygame.mixer.music.get_busy() and self._is_speaking and self._is_running:
                                time.sleep(0.025)
                            played_neural = True
                except Exception as e:
                    print(f"[TTS] Neural playback notice: {e}")
                    played_neural = False

            # 2. Seamless fallback to local Windows SAPI5 (offline)
            if not played_neural:
                try:
                    if self._spk is not None:
                        # Set modulated prosody rate
                        self._spk.Rate = prosody["sapi_rate"]
                        # Native SAPI async speech with interrupt polling
                        self._spk.Speak(clean, 1)  # 1 = SVSFlagsAsync
                        while self._is_speaking and self._is_running:
                            done = self._spk.WaitUntilDone(35)
                            if done:
                                break
                    elif engine is not None:
                        engine.say(clean)
                        engine.runAndWait()
                except Exception as e:
                    print(f"[TTS] Speech playback notice: {e}")
            self._is_speaking = False
            try:
                from voice.aec_guard import aec_guard
                aec_guard.set_speaker_active(False)
            except Exception:
                pass

            # If it was a single one-shot speak call and queue is empty, finalize immediately
            if action == "speak" and self._queue.empty():
                self._session_active = False
                self._stream_closed = False
                self.speech_finished.emit()

            self._queue.task_done()

    def speak(self, text: str):
        """Enqueues full text for speaking, clearing any backlog."""
        if not self._is_enabled or not text:
            return
        with self._queue.mutex:
            self._queue.queue.clear()
        self._stream_closed = False
        self._queue.put(("speak", text))

    def stream_sentence(self, sentence: str):
        """Enqueues a single sentence chunk into the streaming speech pipeline without clearing queue."""
        if not self._is_enabled or not sentence:
            return
        self._stream_closed = False
        self._queue.put(("sentence", sentence))

    def finish_stream(self):
        """Notifies the engine that sentence streaming for the current response has ended."""
        if not self._is_enabled:
            return
        self._queue.put(("finish_stream", None))

    def create_sentence_streamer(self) -> SentenceStreamBuffer:
        """Creates a buffer to attach to LLM streaming token callbacks."""
        return SentenceStreamBuffer(
            on_sentence_ready=self.stream_sentence,
            on_stream_finished=self.finish_stream
        )

    def stop(self):
        """Immediately halts active speech with 0ms latency."""
        with self._queue.mutex:
            self._queue.queue.clear()
        self._is_speaking = False
        self._session_active = False
        self._stream_closed = False

        if HAS_PYGAME:
            try:
                pygame.mixer.music.stop()
            except Exception:
                pass

        if self._spk is not None:
            try:
                # Flag 3 = SVSFPurgeBeforeSpeak (2) | SVSFlagsAsync (1)
                self._spk.Speak("", 3)
            except Exception:
                pass

        try:
            from voice.aec_guard import aec_guard
            aec_guard.set_speaker_active(False)
        except Exception:
            pass

        self.speech_finished.emit()

    def shutdown(self):
        """Halts the TTS worker thread."""
        self._is_running = False
        self.stop()
        self._queue.put(None)
        self.wait(1000)


# Global Singleton Instance
tts = TTSEngine()

