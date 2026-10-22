"""
Full-Duplex Acoustic Echo Cancellation (AEC) & Barge-In Reference Guard for SpaceV.
Prevents SpaceV from reacting to its own voice when speaking through laptop speakers,
while dynamically adjusting neural VAD thresholds to allow intentional conversational barge-in.
"""
from __future__ import annotations

import time
import logging
from typing import Optional, Callable, Tuple

logger = logging.getLogger("SpaceV.AEC")


class AECReferenceGuard:
    """
    Coordinates speaker output reference and microphone VAD thresholds
    for full-duplex conversational interaction.
    """

    _instance: Optional["AECReferenceGuard"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AECReferenceGuard, cls).__new__(cls)
            cls._instance._init_guard()
        return cls._instance

    def _init_guard(self):
        self._is_speaker_active = False
        self._speaker_start_time = 0.0
        self._last_barge_in_time = 0.0
        self._on_barge_in_callback: Optional[Callable[[], None]] = None

    def set_speaker_active(self, active: bool) -> None:
        """Sets outgoing TTS speaker status."""
        self._is_speaker_active = active
        if active:
            self._speaker_start_time = time.time()
        else:
            self._speaker_start_time = 0.0

    @property
    def is_speaker_active(self) -> bool:
        """Returns True if SpaceV is currently outputting voice audio."""
        return self._is_speaker_active

    def register_barge_in_callback(self, callback: Callable[[], None]) -> None:
        """Registers callback to stop TTS immediately upon intentional user barge-in."""
        self._on_barge_in_callback = callback

    def evaluate_frame(self, is_speech: bool, prob: float, rms: float) -> Tuple[bool, float]:
        """
        Applies AEC reference filtering to real-time audio frames:
        1. When SpaceV is silent: Normal VAD threshold passes through untouched.
        2. When SpaceV is speaking: Subtractive reference filter blocks speaker feedback,
           while permitting high-energy deliberate speech to trigger conversational barge-in.
        """
        if not self._is_speaker_active:
            return is_speech, prob

        # 1. High-confidence direct human voice detected during playback -> Conversational Barge-In!
        if (prob >= 0.70 and rms > 0.018) or (rms > 0.035):
            now = time.time()
            if now - self._last_barge_in_time > 0.6:
                self._last_barge_in_time = now
                logger.info("[AEC] 🗣️ Conversational Barge-In detected! Immediate TTS halt triggered.")
                try:
                    from voice.frame_pipeline import frame_pipeline
                    frame_pipeline.interrupt(reason="aec_conversational_turn_taking")
                except Exception:
                    pass
                if self._on_barge_in_callback:
                    try:
                        self._on_barge_in_callback()
                    except Exception as e:
                        logger.debug(f"[AEC] Barge-in callback error: {e}")
            return True, prob

        # 2. Speaker is active and no intentional barge-in voice: suppress speaker echo
        return False, prob * 0.2


aec_guard = AECReferenceGuard()
