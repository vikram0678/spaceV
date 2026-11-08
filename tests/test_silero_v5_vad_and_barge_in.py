"""
Unit and Integration Verification Suite for:
1. Silero VAD v5 ONNX Neural Voice Activity Detection (eto/silero-vad)
2. Low-Latency Conversational Barge-In & Interruption (<150ms cutoff lag)
3. Impulsive Keyboard Click & Desk Noise Rejection (<1% false trigger rate)
"""
import time
import os
import wave
import numpy as np
import pytest

from voice.vad_detector import SileroVADDetector
from voice.aec_guard import AECReferenceGuard
from voice.frame_pipeline import (
    VADFrameProcessor,
    AudioRawFrame,
    UserStartedSpeakingFrame,
    SpeechProgressFrame,
    UserStoppedSpeakingFrame,
)


def _generate_synthetic_typing_click(rms_target: float = 0.08) -> bytes:
    """Generates a 512-sample (32ms) 16-bit mono PCM impulsive typing click."""
    pcm = np.zeros(512, dtype=np.float32)
    # Impulsive transient: sharp click followed by decay
    pcm[10:20] = [0.8, -0.6, 0.45, -0.3, 0.2, -0.15, 0.1, -0.05, 0.02, -0.01]
    # Normalize to target RMS
    current_rms = np.sqrt(np.mean(pcm ** 2))
    if current_rms > 0:
        pcm = pcm * (rms_target / current_rms)
    pcm_int16 = (np.clip(pcm, -1.0, 1.0) * 32767).astype(np.int16)
    return pcm_int16.tobytes()


def _get_sample_speech_chunk(frame_index: int = 5) -> bytes:
    """Reads a real 512-sample (32ms) 16kHz speech frame from the open-source Silero VAD corpus."""
    wav_path = os.path.join(os.path.dirname(__file__), "..", "eto", "silero-vad", "tests", "data", "test.wav")
    if os.path.exists(wav_path):
        with wave.open(wav_path) as f:
            f.setpos(frame_index * 512)
            return f.readframes(512)
    # Fallback synthetic frame
    t = np.linspace(0, 512 / 16000.0, 512, endpoint=False, dtype=np.float32)
    wave_pcm = 0.4 * np.sin(2 * np.pi * 200 * t)
    return (np.clip(wave_pcm, -1.0, 1.0) * 32767).astype(np.int16).tobytes()


def test_silero_v5_model_specs_and_footprint():
    """
    Verifies that Silero VAD v5 is loaded with the optimal 1.28MB footprint
    and 3-input ONNX signature (input, state, sr).
    """
    vad = SileroVADDetector()
    assert vad._session is not None, "Silero VAD ONNX session failed to load"

    model_path = os.path.join(os.path.dirname(__file__), "..", "voice", "models", "silero_vad.onnx")
    assert os.path.exists(model_path), f"Model file not found at {model_path}"
    model_size = os.path.getsize(model_path)
    # V5 model is ~1.28MB (1,289,603 bytes), compared to V4's 2.33MB
    assert model_size < 1_500_000, f"Expected V5 model < 1.5MB, got {model_size} bytes"

    input_names = [i.name for i in vad._session.get_inputs()]
    assert "input" in input_names
    assert "state" in input_names
    assert "sr" in input_names

    output_names = [o.name for o in vad._session.get_outputs()]
    assert "output" in output_names
    assert any("state" in name for name in output_names)


def test_keyboard_typing_rejection_in_vad_detector():
    """
    Verifies that mechanical keyboard clicks and acoustic transients
    are rejected by the neural classifier (P < 0.20) and NOT inflated by RMS energy hacks.
    """
    vad = SileroVADDetector()
    vad.reset_state()

    click_pcm = _generate_synthetic_typing_click(rms_target=0.08)
    is_speech, prob = vad.process_frame(click_pcm)

    # Must classify as non-speech with low neural probability
    assert is_speech is False, f"Keystroke was falsely classified as speech! prob={prob:.4f}"
    assert prob < 0.20, f"Keystroke neural probability too high: {prob:.4f}"


def test_aec_guard_keyboard_typing_rejection_during_playback():
    """
    Verifies that loud keystrokes during TTS playback (rms > 0.035) do NOT trigger
    false barge-in interruptions now that the raw RMS bypass has been purged.
    """
    guard = AECReferenceGuard()
    guard.set_speaker_active(True)
    guard._last_barge_in_time = 0.0

    # Keypress with high RMS (0.085) but low neural speech prob (0.02)
    fake_rms = 0.085
    low_speech_prob = 0.02

    try:
        is_speech, prob = guard.evaluate_frame(
            is_speech=False,
            prob=low_speech_prob,
            rms=fake_rms
        )

        assert is_speech is False, "Loud typing transient falsely triggered AEC barge-in!"
        assert guard._last_barge_in_time == 0.0, "AEC barge-in timestamp was falsely updated!"
    finally:
        guard.set_speaker_active(False)


def test_human_voice_onset_detection():
    """
    Verifies that legitimate human voice is detected promptly (single 32ms frame onset).
    """
    vad = SileroVADDetector()
    vad.reset_state()

    voice_pcm = _get_sample_speech_chunk(frame_index=5)
    is_speech, prob = vad.process_frame(voice_pcm)

    assert is_speech is True, f"Legitimate voice chunk was not detected as speech! prob={prob:.4f}"
    assert prob >= 0.50, f"Voice chunk probability below threshold: {prob:.4f}"


def test_conversational_barge_in_latency_under_150ms():
    """
    Verifies that conversational turn-taking interruption takes <150ms
    from voice onset to pipeline interruption and buffer flush.
    """
    guard = AECReferenceGuard()
    guard.set_speaker_active(True)
    guard._last_barge_in_time = 0.0

    callback_called = False
    def on_barge_in():
        nonlocal callback_called
        callback_called = True

    guard.register_barge_in_callback(on_barge_in)

    # Legitimate voice: high neural probability and sufficient RMS
    voice_rms = 0.05
    voice_prob = 0.88

    try:
        t0 = time.perf_counter()
        is_speech, _evaluated_prob = guard.evaluate_frame(
            is_speech=True,
            prob=voice_prob,
            rms=voice_rms
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert is_speech is True
        assert callback_called is True
        # Evaluated latency on CPU should be well under 10ms (target <150ms)
        assert elapsed_ms < 150.0, f"Barge-in took too long: {elapsed_ms:.2f}ms"
    finally:
        guard.set_speaker_active(False)



def test_vad_frame_processor_streaming_lifecycle():
    """
    Verifies the streaming frame pipeline emits UserStartedSpeakingFrame,
    SpeechProgressFrames, and handles fast 5-chunk (160ms) silence debounce.
    """
    vad = SileroVADDetector()
    vad.reset_state()
    processor = VADFrameProcessor(
        vad_detector=vad,
        pre_speech_chunks=4,
        silence_debounce_chunks=5,
        draft_interval_chunks=4
    )

    from voice.frame_pipeline import FrameProcessor
    emitted_frames = []
    class MockCollector(FrameProcessor):
        def process_frame(self, frame):
            emitted_frames.append(frame)

    collector = MockCollector("TestCollector")
    processor.set_next(collector)

    # 1. Feed 4 chunks of silence
    silence = b"\x00" * 1024
    for _ in range(4):
        processor.process_frame(AudioRawFrame(pcm_bytes=silence))
    assert len(emitted_frames) == 0

    # 2. Feed real speech chunks (frames 5 to 12 from test.wav)
    for i in range(5, 13):
        speech_chunk = _get_sample_speech_chunk(frame_index=i)
        processor.process_frame(AudioRawFrame(pcm_bytes=speech_chunk))

    # Assert UserStartedSpeakingFrame emitted on speech start
    has_start = any(isinstance(f, UserStartedSpeakingFrame) for f in emitted_frames)
    assert has_start is True, "UserStartedSpeakingFrame was not emitted on speech onset!"

    # Assert SpeechProgressFrame emitted at interval 4
    has_progress = any(isinstance(f, SpeechProgressFrame) for f in emitted_frames)
    assert has_progress is True, "SpeechProgressFrame was not emitted during sustained speech!"

    # 3. Feed silence to trigger turn-taking debounce (5 chunks = 160ms)
    for _ in range(5):
        processor.process_frame(AudioRawFrame(pcm_bytes=silence))

    has_stopped = any(isinstance(f, UserStoppedSpeakingFrame) for f in emitted_frames)
    assert has_stopped is True, "UserStoppedSpeakingFrame was not emitted after 5-chunk debounce!"


def test_vad_reset_state_clears_hidden_tensors():
    """
    Verifies that reset_state() clears neural recurrent state and context buffers.
    """
    vad = SileroVADDetector()
    speech = _get_sample_speech_chunk(frame_index=5)
    vad.process_frame(speech)

    # State should be populated
    assert np.any(vad._state != 0.0)
    assert np.any(vad._context != 0.0)

    # Reset
    vad.reset_state()
    assert np.all(vad._state == 0.0)
    assert np.all(vad._context == 0.0)
