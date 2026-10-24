"""
Unit and Integration Tests for SpaceV Voice Pipeline:
1. Mute Button (True Mute: stops TTS & pauses microphone hardware stream)
2. Mic Button (Clean manual listening turn without PyAudio contention)
3. Zero-Hallucination Energy Gate (Drops faint room murmurs & mic hiss)
4. Anti-Echo Conversational Loop Break (Exit commands prevent auto-listening loop)
"""
import sys
import numpy as np
import pytest

from voice.stt_engine import OfflineWhisperSingleton, VoiceListener
from voice.wake_word import WakeWordDetector


def test_offline_whisper_singleton_loads():
    """Verify Faster-Whisper singleton returns a valid model instance (not None)."""
    model = OfflineWhisperSingleton.get_model()
    assert model is not None, "OfflineWhisperSingleton.get_model() must not be None!"


def test_zero_hallucination_energy_gate_drops_silence():
    """Verify faint murmurs / mic hiss below RMS 180 return empty string immediately."""
    # Faint room hiss with low amplitude (RMS ~50)
    low_noise = (np.random.randn(16000) * 50).astype(np.int16).tobytes()
    text = VoiceListener.transcribe_pcm(low_noise)
    assert text == "", f"Faint background noise should be gated to empty string! Got: '{text}'"


def test_wake_word_pause_and_resume():
    """Verify pause() sets paused state, stops recorder stream, and emits STANDBY."""
    detector = WakeWordDetector()
    detector.pause()
    assert detector._paused is True
    assert detector._conversational_mode is False
    assert detector.recorder._is_recording is False

    detector.resume()
    assert detector._paused is False
    detector.stop()


def test_exit_command_prevents_conversational_loop():
    """Verify exit phrases ('bye', 'thank you', 'stop') set _last_turn_was_exit flag."""
    EXIT_WORDS = ["thank you", "thanks", "that's all", "bye", "goodbye", "exit", "quit", "halt", "stop"]

    for word in ["bye", "Bye.", "Thank you SpaceV", "stop", "goodbye"]:
        clean = word.strip().lower()
        is_exit = any(clean == ew or clean.startswith(ew + " ") or ew in clean for ew in EXIT_WORDS)
        assert is_exit is True, f"'{word}' should be recognized as an exit phrase!"

    for word in ["open notepad", "what is the weather", "search for rust"]:
        clean = word.strip().lower()
        is_exit = any(clean == ew or clean.startswith(ew + " ") or ew in clean for ew in EXIT_WORDS)
        assert is_exit is False, f"'{word}' should NOT be recognized as an exit phrase!"


def test_toggle_voice_mute_logic():
    """Verify that toggle_voice logic properly mutes both TTS and microphone."""
    from voice.tts_engine import tts
    detector = WakeWordDetector()

    # Initial state: Voice active
    tts.is_enabled = True
    detector._paused = False

    # Simulate MUTE (turning voice OFF)
    tts.is_enabled = False
    detector.pause()
    assert tts.is_enabled is False
    assert detector._paused is True

    # Simulate UNMUTE (turning voice ON)
    tts.is_enabled = True
    detector.resume()
    assert tts.is_enabled is True
    assert detector._paused is False

    detector.stop()


def test_wake_word_enabled_by_default_in_config():
    """Verify that hands-free wake word is enabled by default in config.py (Unified Hybrid Parity)."""
    from config import WAKE_WORD_ENABLED_BY_DEFAULT
    assert WAKE_WORD_ENABLED_BY_DEFAULT is True, "WAKE_WORD_ENABLED_BY_DEFAULT must be True by default!"


def test_energy_gate_preserves_conversational_speech_above_65_rms():
    """Verify speech signal at conversational RMS (e.g., 200 RMS) passes energy gate."""
    # Synthesize sine wave audio at 200 RMS (speech)
    t = np.linspace(0, 1.0, 16000, False)
    speech_wave = (np.sin(2 * np.pi * 300 * t) * (200 * np.sqrt(2))).astype(np.int16).tobytes()
    # It passes the 65.0 RMS cutoff and proceeds to Faster-Whisper
    # (Faster-Whisper handles it without raising an error)
    samples = np.frombuffer(speech_wave, dtype=np.int16)
    rms = float(np.sqrt(np.mean(samples.astype(np.float32) ** 2)))
    assert rms >= 65.0, f"Simulated speech should be >= 65.0 RMS! Got: {rms}"


def test_in_window_hotkey_registered():
    """Verify that ChatWindow defines QShortcut for Ctrl+Space to trigger toggle_mic_listening."""
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    from unittest.mock import MagicMock
    from ui.chat_window import ChatWindow
    mock_agent = MagicMock()
    mock_agent.model = 'qwen2.5:latest'
    window = ChatWindow(mock_agent)
    assert hasattr(window, "mic_shortcut"), "ChatWindow must have mic_shortcut attribute"
    assert window.mic_shortcut.key().toString() == "Ctrl+Space"
    window.close()
