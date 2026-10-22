"""
Real-time Audio Stream Ingestion & Ring-Buffered Framing for SpaceV.
Inspired by RealtimeSTT and Handy's audio pipeline.
Captures 16kHz 16-bit Mono PCM chunks with pre-speech buffering and VAD turn detection.
"""
from __future__ import annotations

import collections
import io
import logging
import threading
import time
import wave

from voice.vad_detector import SileroVADDetector

logger = logging.getLogger("SpaceV.AudioStream")

try:
    import pyaudio
    HAS_PYAUDIO = True
except ImportError:
    HAS_PYAUDIO = False


class AudioStreamRecorder:
    """
    Manages non-blocking real-time audio capture with pre-speech ring buffering.
    Preserves opening consonants using a sliding history window.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        chunk_size: int = 512,  # 32 ms at 16kHz (Standard Silero VAD frame)
        pre_speech_chunks: int = 10,  # ~320 ms of pre-speech ring buffer (preserves initial consonants)
        silence_debounce_chunks: int = 13,  # ~416 ms of post-speech silence for rapid conversational turn-taking
        vad: SileroVADDetector | None = None,
    ):
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.bytes_per_chunk = chunk_size * 2  # 16-bit = 2 bytes per sample
        self.pre_speech_chunks = pre_speech_chunks
        self.silence_debounce_chunks = silence_debounce_chunks

        self.vad = vad or SileroVADDetector(sample_rate=sample_rate)
        self._pa: pyaudio.PyAudio | None = None
        self._stream: pyaudio.Stream | None = None
        self._is_recording = False
        self._lock = threading.Lock()

        # Ring buffer for pre-speech frames
        self._pre_buffer = collections.deque(maxlen=self.pre_speech_chunks)

    def start_stream(self) -> bool:
        """Opens the hardware microphone stream."""
        if not HAS_PYAUDIO:
            logger.error("[AudioStream] PyAudio is not installed.")
            return False

        with self._lock:
            if self._is_recording:
                return True

            try:
                # Suppress low-level ALSA/JACK C stderr probing messages on Linux/WSL2
                import os
                try:
                    null_fd = os.open(os.devnull, os.O_RDWR)
                    orig_stderr = os.dup(2)
                    os.dup2(null_fd, 2)
                    self._pa = pyaudio.PyAudio()
                finally:
                    os.dup2(orig_stderr, 2)
                    os.close(orig_stderr)
                    os.close(null_fd)

                self._stream = self._pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                )
                self._is_recording = True
                self._pre_buffer.clear()
                self.vad.reset_state()
                logger.info("[AudioStream] 🎙️ Hardware mic stream opened (16kHz 16-bit Mono).")
                return True
            except Exception as e:
                logger.error(f"[AudioStream] Failed to open mic stream: {e}")
                self._cleanup()
                return False

    def stop_stream(self) -> None:
        """Closes the hardware microphone stream."""
        with self._lock:
            self._cleanup()

    def _cleanup(self) -> None:
        self._is_recording = False
        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None

        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def read_chunk(self) -> bytes | None:
        """Reads a single raw PCM frame from the audio stream (thread-safe)."""
        with self._lock:
            if not self._is_recording or not self._stream:
                return None
            try:
                return self._stream.read(self.chunk_size, exception_on_overflow=False)
            except Exception as e:
                logger.debug(f"[AudioStream] Read chunk error: {e}")
                return None

    def record_utterance(
        self,
        timeout: float = 6.0,
        phrase_limit: float = 12.0,
        stop_check=None,
    ) -> bytes | None:
        """
        Records a complete spoken phrase bounded by Silero VAD turn detection.
        Returns:
            Raw PCM audio bytes of the complete utterance with pre-speech padding,
            or None if timed out without speech.
        """
        if not self.start_stream():
            return None

        self.vad.reset_state()
        self._pre_buffer.clear()

        start_time = time.time()
        speech_started = False
        silence_counter = 0
        recorded_frames = []

        try:
            while self._is_recording:
                if stop_check and stop_check():
                    break

                now = time.time()
                elapsed = now - start_time

                # Initial timeout waiting for speech
                if not speech_started and elapsed > timeout:
                    logger.debug("[AudioStream] Timeout waiting for speech onset.")
                    break

                # Max phrase limit
                if speech_started and elapsed > phrase_limit:
                    logger.debug("[AudioStream] Phrase time limit reached.")
                    break

                chunk = self.read_chunk()
                if not chunk:
                    time.sleep(0.01)
                    continue

                is_speech, prob = self.vad.process_frame(chunk)

                if not speech_started:
                    self._pre_buffer.append(chunk)
                    if is_speech:
                        speech_started = True
                        recorded_frames.extend(self._pre_buffer)
                        logger.debug(f"[AudioStream] ⚡ Speech onset detected! (prob={prob:.2f})")
                else:
                    recorded_frames.append(chunk)
                    if not is_speech:
                        silence_counter += 1
                        if silence_counter >= self.silence_debounce_chunks:
                            logger.debug(f"[AudioStream] Turn complete after {silence_counter} silence frames.")
                            break
                    else:
                        silence_counter = 0

            if not speech_started or len(recorded_frames) < 10:
                return None

            return b"".join(recorded_frames)

        finally:
            self.stop_stream()

    @staticmethod
    def pcm_to_wav_bytes(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
        """Converts raw 16-bit mono PCM bytes into standard WAV container bytes."""
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)  # 16-bit = 2 bytes
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(pcm_bytes)
        return wav_io.getvalue()
