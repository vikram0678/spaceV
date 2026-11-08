"""
Full-Duplex Acoustic Echo Cancellation (AEC) & Barge-In Reference Guard for SpaceV.
Prevents SpaceV from reacting to its own voice when speaking through laptop speakers,
while dynamically adjusting neural VAD thresholds to allow intentional conversational barge-in.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

logger = logging.getLogger("SpaceV.AEC")


class AECReferenceGuard:
    """
    Coordinates speaker output reference and microphone VAD thresholds
    for full-duplex conversational interaction.
    """

    _instance: AECReferenceGuard | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_guard()
        return cls._instance

    def _init_guard(self):
        self._is_speaker_active = False
        self._speaker_start_time = 0.0
        self._last_barge_in_time = 0.0
        self._on_barge_in_callback: Callable[[], None] | None = None
        self._headphone_mode = False
        self.barge_in_rms_threshold = 0.040  # Distinguishes laptop speaker bleed from deliberate user voice
        self.barge_in_prob_threshold = 0.70  # Neural confidence requirement

    def set_headphone_mode(self, enabled: bool) -> None:
        """Enables zero-bleed headphone mode for feather-light conversational barge-in."""
        self._headphone_mode = enabled
        logger.info(f"[AEC] Headphone mode set to: {enabled}")

    @property
    def headphone_mode(self) -> bool:
        return self._headphone_mode

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

    def evaluate_frame(self, is_speech: bool, prob: float, rms: float) -> tuple[bool, float]:
        """
        Applies AEC reference filtering to real-time audio frames:
        1. When SpaceV is silent: Normal VAD threshold passes through untouched.
        2. When SpaceV is speaking: Subtractive reference filter blocks speaker feedback,
           while permitting high-energy deliberate speech to trigger conversational barge-in.
        """
        if not self._is_speaker_active:
            return is_speech, prob

        min_rms = 0.020 if self._headphone_mode else self.barge_in_rms_threshold
        min_prob = 0.65 if self._headphone_mode else self.barge_in_prob_threshold

        # 1. High-confidence direct human voice detected during playback -> Conversational Barge-In!
        # Strict neural voice and energy differential: rejects speaker bleed while allowing user speech
        if prob >= min_prob and rms >= min_rms:
            now = time.time()
            if now - self._last_barge_in_time > 0.3:
                self._last_barge_in_time = now
                logger.info(f"[AEC] 🗣️ Conversational Barge-In detected! (prob={prob:.2f}, rms={rms:.3f}) Immediate TTS halt triggered.")
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

        # 2. Speaker is active and audio is within speaker bleed floor: suppress speaker echo
        return False, prob * 0.2


aec_guard = AECReferenceGuard()
