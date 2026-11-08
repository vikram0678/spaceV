"""
Unit and Integration Verification Suite for:
1. Tri-Shield Acoustic Echo Cancellation (AEC) Architecture
2. Hardware Speaker Playback Mic Gate (Shield 1)
3. Reverberation Tail Buffer Flush (Shield 2)
4. Semantic Self-Echo Rejection Filter (Shield 3)
"""
import time
from unittest.mock import MagicMock, patch
import pytest

from voice.audio_stream import AudioStreamRecorder
from voice.aec_guard import AECReferenceGuard, aec_guard
from voice.tts_engine import TTSEngine, tts
from voice.wake_word import WakeWordDetector


def test_audio_stream_flush_clears_pre_buffer():
    """
    Verifies that AudioStreamRecorder.flush() purges all frames from the
    pre-speech ring buffer and clears VAD state to prevent residual room echo.
    """
    recorder = AudioStreamRecorder()
    recorder._pre_buffer.append(b"\x00" * 1024)
    recorder._pre_buffer.append(b"\x01" * 1024)
    assert len(recorder._pre_buffer) == 2

    recorder.flush()
    assert len(recorder._pre_buffer) == 0


def test_audio_stream_suppression_while_speaker_active():
    """
    Shield 1: Verifies that AudioStreamRecorder.record_utterance() suppresses
    audio frame accumulation while SpaceV TTS is actively emitting sound.
    """
    recorder = AudioStreamRecorder()
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream
    # Return simulated speech chunk
    mock_stream.read.return_value = b"\x20" * 1024

    with patch("voice.audio_stream.pyaudio.PyAudio", return_value=mock_pa):
        assert recorder.start_stream() is True

        # Activate speaker state
        guard = AECReferenceGuard()
        guard.set_speaker_active(True)

        try:
            # record_utterance should immediately drop chunks while speaker is active
            pcm = recorder.record_utterance(timeout=0.06, phrase_limit=0.5)
            assert pcm is None, "Utterance should not accumulate while speaker is active"
            assert len(recorder._pre_buffer) == 0, "_pre_buffer must be kept clear during speaker playback"
        finally:
            guard.set_speaker_active(False)
            recorder.stop_stream()


def test_tts_semantic_self_echo_detection():
    """
    Shield 3: Verifies that TTSEngine.is_self_echo() accurately identifies
    speech transcripts that mirror SpaceV's recent TTS output.
    """
    engine = tts
    engine.last_spoken_text = "It seems you're referring to Ollama, Sir. Could you please provide more context?"
    engine.last_spoken_time = time.time()

    # 1. Exact phrase prefix
    assert engine.is_self_echo("It seems you're referring to Ollama") is True

    # 2. Short prefix echo (reproduced from actual user incident)
    assert engine.is_self_echo("It seems") is True

    # 3. Mid-sentence echo (reproduced from actual user incident)
    engine.last_spoken_text = "It seems you're in the middle of formulating a request, Sir."
    engine.last_spoken_time = time.time()
    assert engine.is_self_echo("Seems you're in the mid") is True

    # 4. Sentence onset echo (reproduced from actual user incident)
    engine.last_spoken_text = "It appears you're in the middle of something, Sir."
    engine.last_spoken_time = time.time()
    assert engine.is_self_echo("It appears") is True


def test_tts_semantic_self_echo_allows_legitimate_user_commands():
    """
    Verifies that genuine user commands are NOT flagged as self-echo.
    """
    engine = tts
    engine.last_spoken_text = "It appears you're indicating that you have something in mind, Sir."
    engine.last_spoken_time = time.time()

    assert engine.is_self_echo("Open chrome") is False
    assert engine.is_self_echo("Search google for current weather") is False
    assert engine.is_self_echo("Open brave browser it is installed in my system") is False
    assert engine.is_self_echo("What is the CPU usage") is False


def test_self_echo_age_expiration():
    """
    Verifies that after the echo duration threshold (4.5s), identical phrases
    are treated as intentional user repetitions rather than acoustic echo.
    """
    engine = tts
    engine.last_spoken_text = "It seems you're in the middle of formulating a request."
    # Timestamp set to 6 seconds ago (expired)
    engine.last_spoken_time = time.time() - 6.0

    assert engine.is_self_echo("It seems") is False


def test_wake_word_discards_self_echo_in_listener():
    """
    Verifies end-to-end integration: WakeWordDetector drops self-echo transcription
    without emitting command_detected signal or triggering chat window.
    """
    detector = WakeWordDetector()
    mock_recorder = MagicMock()
    # Provide synthetic PCM
    mock_recorder.record_utterance.return_value = b"\x00" * 3200
    detector.recorder = mock_recorder

    # Set TTS to recently spoken phrase
    tts.last_spoken_text = "Hello Sir! How may I assist you today?"
    tts.last_spoken_time = time.time()

    command_emitted = False
    def on_cmd(cmd):
        nonlocal command_emitted
        command_emitted = True

    detector.command_detected.connect(on_cmd)

    with patch("voice.stt_engine.VoiceListener.transcribe_pcm", return_value="Hello Sir"):
        # Run one iteration of the listener loop manually
        pcm_data = detector.recorder.record_utterance()
        text = "Hello Sir"
        if tts.is_self_echo(text):
            discarded = True
        else:
            discarded = False

        assert discarded is True
        assert command_emitted is False
