"""
Modern Voice & Acoustic Processing Package for SpaceV.
Integrates Silero VAD, Realtime Audio Ring-Buffering, Streaming STT,
Hands-Free Wake Detection, Non-Blocking TTS, and Desktop Dictation.
"""
from voice.vad_detector import SileroVADDetector
from voice.audio_stream import AudioStreamRecorder
from voice.stt_engine import VoiceListener
from voice.wake_word import WakeWordDetector
from voice.dictation_manager import dictation_manager, DictationManager
from voice.tts_engine import tts, TTSEngine

__all__ = [
    "SileroVADDetector",
    "AudioStreamRecorder",
    "VoiceListener",
    "WakeWordDetector",
    "dictation_manager",
    "DictationManager",
    "tts",
    "TTSEngine",
]
