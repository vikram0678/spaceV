"""
Unit and Integration Tests for SpaceV Persistent Warm Stream Resilience.
Verifies:
1. Zero-churn stream persistence across consecutive silent conversational timeouts.
2. Prevention of PortAudio / PulseAudio Pa_Terminate mainloop assertions.
3. Clean pause/resume lifecycle management for mic mute & background standby.
4. Exception shielding against stream overflow/underflow.
"""
import time
from unittest.mock import MagicMock, patch
import pytest

from voice.audio_stream import AudioStreamRecorder
from voice.wake_word import WakeWordDetector


def test_persistent_stream_across_consecutive_silence_timeouts():
    """
    Verify that record_utterance() does NOT close the stream or terminate
    PyAudio between consecutive silent conversational turns.
    """
    recorder = AudioStreamRecorder()
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream
    # Return 512 samples of 16-bit silence
    mock_stream.read.return_value = b"\x00" * 1024

    with patch("voice.audio_stream.pyaudio.PyAudio", return_value=mock_pa):
        # Initial turn opens stream
        assert recorder.start_stream() is True
        assert recorder._is_recording is True

        # Simulate 10 consecutive silent conversational turns (e.g. 3.5s timeout)
        for i in range(10):
            pcm = recorder.record_utterance(timeout=0.04, phrase_limit=0.5)
            assert pcm is None, f"Turn {i} should time out with None"
            # Crucial assertion: Stream must remain warm and active!
            assert recorder._is_recording is True, f"Stream was unexpectedly stopped on turn {i}"
            assert recorder._stream is not None, f"_stream handle was dropped on turn {i}"
            assert mock_pa.terminate.call_count == 0, f"PyAudio.terminate() was called on turn {i}!"

        # Stream should only close when explicitly commanded
        recorder.stop_stream()
        assert recorder._is_recording is False
        assert recorder._stream is None
        assert mock_pa.terminate.call_count == 1


def test_wake_word_detector_pause_and_resume_lifecycle():
    """
    Verify that WakeWordDetector pause() closes the hardware stream and
    resume() reacquires it cleanly.
    """
    detector = WakeWordDetector()
    detector.recorder = MagicMock()
    detector.recorder._is_recording = True

    # Test Pause
    detector.pause()
    assert detector._paused is True
    assert detector._conversational_mode is False
    detector.recorder.stop_stream.assert_called_once()

    # Test Resume
    detector.resume()
    assert detector._paused is False
    detector.recorder.start_stream.assert_called_once()

    # Test Stop
    detector.stop()
    assert detector._is_running is False
    assert detector.recorder.stop_stream.call_count == 2


def test_read_chunk_exception_shielding():
    """
    Verify that read_chunk() safely catches stream errors (e.g. buffer overflow)
    without raising exceptions or dropping the stream.
    """
    recorder = AudioStreamRecorder()
    recorder._is_recording = True
    mock_stream = MagicMock()
    mock_stream.read.side_effect = OSError("Input overflowed")
    recorder._stream = mock_stream

    chunk = recorder.read_chunk()
    assert chunk is None, "read_chunk should return None on exception"
    assert recorder._is_recording is True, "read_chunk should not alter _is_recording on read error"


def test_auto_stop_flag_compatibility():
    """
    Verify that auto_stop=True can still be requested if single-shot caller requires it.
    """
    recorder = AudioStreamRecorder()
    mock_pa = MagicMock()
    mock_stream = MagicMock()
    mock_pa.open.return_value = mock_stream
    mock_stream.read.return_value = b"\x00" * 1024

    with patch("voice.audio_stream.pyaudio.PyAudio", return_value=mock_pa):
        pcm = recorder.record_utterance(timeout=0.03, auto_stop=True)
        assert pcm is None
        # With auto_stop=True, stream is stopped
        assert recorder._is_recording is False
        assert mock_pa.terminate.call_count == 1
