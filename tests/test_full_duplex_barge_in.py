"""
Unit and Integration Tests for Full-Duplex Continuous Voice Interaction & Conversational Barge-In.
Verifies that SpaceV allows users to speak and interrupt the assistant mid-sentence (Google Assistant / Siri style)
while rejecting laptop speaker bleed and typing noise.
"""
import time
from unittest.mock import MagicMock, patch

from voice.aec_guard import AECReferenceGuard, aec_guard
from voice.audio_stream import AudioStreamRecorder


def test_full_duplex_speaker_bleed_suppressed():
    """
    Verifies that normal laptop speaker bleed (RMS < 0.040 or non-speech)
    is suppressed during TTS playback without accumulating an utterance.
    """
    recorder = AudioStreamRecorder()
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream
    # Simulate low-amplitude acoustic bleed
    mock_stream.read.return_value = b"\x00" * 1024

    with patch("voice.audio_stream.pyaudio.PyAudio", return_value=mock_pa):
        assert recorder.start_stream() is True
        guard = AECReferenceGuard()
        guard.set_speaker_active(True)
        try:
            pcm = recorder.record_utterance(timeout=0.08, phrase_limit=0.5)
            assert pcm is None, "Speaker bleed must not trigger utterance recording!"
            assert len(recorder._pre_buffer) == 0, "_pre_buffer must be empty during speaker bleed"
        finally:
            guard.set_speaker_active(False)
            recorder.stop_stream()


def test_full_duplex_user_barge_in_interrupts_tts_and_captures():
    """
    Verifies that deliberate near-field user speech (prob >= 0.70, RMS >= 0.040)
    during TTS playback triggers immediate barge-in, halts TTS, and engages capture.
    """
    guard = AECReferenceGuard()
    guard.set_speaker_active(True)
    guard._last_barge_in_time = 0.0

    barge_in_halted = False
    def mock_tts_stop():
        nonlocal barge_in_halted
        barge_in_halted = True
        guard.set_speaker_active(False)

    guard.register_barge_in_callback(mock_tts_stop)

    # Frame 1: Normal speaker bleed (below threshold)
    is_speech, prob = guard.evaluate_frame(is_speech=True, prob=0.60, rms=0.025)
    assert is_speech is False
    assert barge_in_halted is False

    # Frame 2: User says "Stop" directly into the mic (prob=0.85, rms=0.065)
    t0 = time.perf_counter()
    is_speech, prob = guard.evaluate_frame(is_speech=True, prob=0.85, rms=0.065)
    latency_ms = (time.perf_counter() - t0) * 1000.0

    assert is_speech is True
    assert barge_in_halted is True
    assert not guard.is_speaker_active
    assert latency_ms < 50.0, f"Barge-in callback too slow: {latency_ms:.2f}ms"


def test_full_duplex_headphone_mode_whisper_barge_in():
    """
    Verifies that in headphone mode (zero speaker bleed), even quiet whispers
    (RMS >= 0.020, prob >= 0.65) immediately trigger barge-in.
    """
    guard = AECReferenceGuard()
    guard.set_headphone_mode(True)
    guard.set_speaker_active(True)
    guard._last_barge_in_time = 0.0

    halted = False
    guard.register_barge_in_callback(lambda: setattr(guard, "_is_speaker_active", False) or globals().update(halted=True))

    try:
        # Quiet whisper
        is_speech, prob = guard.evaluate_frame(is_speech=True, prob=0.68, rms=0.022)
        assert is_speech is True
        assert not guard.is_speaker_active
    finally:
        guard.set_headphone_mode(False)
        guard.set_speaker_active(False)
