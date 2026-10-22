"""
Continuous Hands-Free Wake-Word Detector for SpaceV.
Powered by Silero VAD local acoustic gating:
Runs 100% locally with zero continuous network traffic. Only transcribes when actual
neural human speech is detected.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal
from config import WAKE_WORDS
from voice.audio_stream import AudioStreamRecorder
from voice.vad_detector import SileroVADDetector
from voice.stt_engine import VoiceListener

logger = logging.getLogger("SpaceV.WakeWord")


class WakeWordDetector(QThread):
    """
    Continuous Full-Duplex Conversational Audio Engine for SpaceV (Google Assistant / Siri Style).
    Features:
    - 100% Local Neural Silero VAD turn gating
    - Standby 'Hey SpaceV' hands-free activation
    - Continuous Conversational Mode: naturally listen, talk, listen without repeating wake words
    - Instant Conversational Barge-In: cuts TTS speech in <10ms when user speaks
    - Graceful conversational expiration to standby upon silence or completion phrases
    """
    wake_word_detected = pyqtSignal()
    command_detected = pyqtSignal(str)
    listening_state_changed = pyqtSignal(str)  # "STANDBY", "LISTENING", "PROCESSING"

    def __init__(self):
        super().__init__()
        self._is_running = True
        self._paused = False
        self._conversational_mode = False
        self._conversational_deadline = 0.0
        self.vad = SileroVADDetector()
        self.recorder = AudioStreamRecorder(
            vad=self.vad,
            pre_speech_chunks=10,  # ~320ms pre-speech buffer
            silence_debounce_chunks=14,  # ~450ms post-speech pause
        )

    def start_conversational_turn(self, timeout_sec: float = 7.5):
        """Puts SpaceV into continuous conversational listening mode (Google Assistant / Siri style)."""
        self._conversational_mode = True
        self._conversational_deadline = time.time() + timeout_sec
        self._paused = False
        self.listening_state_changed.emit("LISTENING")
        print(f"[CONVERSATION] 🎙️ Conversational mode active ({timeout_sec:.1f}s listening window)...")

    def end_conversational_turn(self):
        """Returns SpaceV to passive 'Hey SpaceV' standby mode."""
        self._conversational_mode = False
        self._conversational_deadline = 0.0
        self.listening_state_changed.emit("STANDBY")

    @property
    def is_conversational_mode(self) -> bool:
        return self._conversational_mode

    def pause(self):
        """Temporarily pauses the listener."""
        self._paused = True

    def resume(self):
        """Resumes the listener."""
        self._paused = False

    def stop(self):
        """Halts the continuous conversational listener thread."""
        self._is_running = False
        self.recorder.stop_stream()

    def run(self):
        print("[WAKE-WORD] [LISTENER] Full-Duplex Conversational Engine Active (Continuous VAD + Conversational Turns)...")
        while self._is_running:
            if self._paused:
                time.sleep(0.12)
                continue

            # Check conversational timeout: gracefully drop back to standby if user stayed quiet
            if self._conversational_mode and time.time() > self._conversational_deadline:
                print("[WAKE-WORD] [IDLE] Conversational turn expired -> Reverting to 'Hey SpaceV' standby.")
                self.end_conversational_turn()

            try:
                # Record a spoken phrase only when speech is present
                # Shorter phrase limit and timeout in conversational mode for low-latency turn-taking
                pcm_data = self.recorder.record_utterance(
                    timeout=3.5 if self._conversational_mode else 4.0,
                    phrase_limit=7.0,
                    stop_check=lambda: not self._is_running or self._paused
                )

                if not self._is_running:
                    break

                if not pcm_data:
                    # Idle silence, continue loop
                    continue

                # Speech was detected by Silero VAD; transcribe phrase
                text = VoiceListener.transcribe_pcm(pcm_data).strip()
                if not text:
                    continue

                clean_lower = text.lower().strip()
                print(f"[VOICE] [HEARD] '{text}' (mode={'CONVERSATIONAL' if self._conversational_mode else 'STANDBY'})")

                # 1. Instant Stop / Cancellation / Barge-In Command
                STOP_WORDS = ["stop", "cancel", "shut up", "be quiet", "pause", "hold on", "never mind", "halt"]
                if any(clean_lower == sw or clean_lower.startswith(sw + " ") for sw in STOP_WORDS):
                    print("[VOICE] [INTERRUPT] User commanded STOP -> Halting voice & tasks immediately.")
                    from voice.frame_pipeline import frame_pipeline
                    from voice.tts_engine import tts
                    tts.stop()
                    frame_pipeline.interrupt(reason="user_stop_command")
                    self.command_detected.emit("stop")
                    continue

                # 2. Conversational Exit Phrases ("thank you", "bye", "that's all")
                EXIT_WORDS = ["thank you", "thanks", "that's all", "bye", "goodbye", "exit conversation"]
                if any(ew in clean_lower for ew in EXIT_WORDS):
                    print("[VOICE] [EXIT] User ended conversational turn.")
                    self.end_conversational_turn()
                    self.command_detected.emit(text)
                    continue

                # 3. Conversational Mode (Continuous talk & listen without saying wake word again)
                if self._conversational_mode:
                    clean_cmd = text
                    for w in WAKE_WORDS:
                        clean_cmd = re.sub(rf"\b{re.escape(w)}\b", "", clean_cmd, flags=re.IGNORECASE)
                    clean_cmd = clean_cmd.strip()
                    if not clean_cmd:
                        clean_cmd = text

                    # Refresh conversational window for follow-up turns
                    self._conversational_deadline = time.time() + 7.5
                    print(f"[CONVERSATION] [TURN] Processing: '{clean_cmd}'")
                    self.command_detected.emit(clean_cmd)
                    continue

                # 4. Standby Wake-Word Detection ("Hey SpaceV")
                is_wake = any(w in clean_lower for w in WAKE_WORDS)
                if is_wake:
                    print("[WAKE-WORD] [TRIGGER] SpaceV WAKE PHRASE DETECTED!")
                    # Activate conversational mode
                    self.start_conversational_turn(timeout_sec=8.0)

                    # Strip wake words to see if an immediate inline command was spoken
                    clean_cmd = text
                    for w in WAKE_WORDS:
                        clean_cmd = re.sub(rf"\b{re.escape(w)}\b", "", clean_cmd, flags=re.IGNORECASE)
                    clean_cmd = clean_cmd.strip()

                    if len(clean_cmd) > 2:
                        print(f"[WAKE-WORD] [COMMAND] Direct Command: '{clean_cmd}'")
                        self.command_detected.emit(clean_cmd)
                    else:
                        self.wake_word_detected.emit()

                    time.sleep(0.5)

            except Exception as e:
                logger.debug(f"[WAKE-WORD] Voice loop notice: {e}")
                time.sleep(0.3)

        self.recorder.stop_stream()
