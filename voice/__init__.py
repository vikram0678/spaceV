"""
Modern Voice & Acoustic Processing Package for SpaceV.
Integrates Silero VAD, Realtime Audio Ring-Buffering, Streaming STT,
Hands-Free Wake Detection, Non-Blocking TTS, and Desktop Dictation.
"""
from voice.audio_stream import AudioStreamRecorder
from voice.dictation_manager import DictationManager, dictation_manager
from voice.stt_engine import VoiceListener
from voice.tts_engine import TTSEngine, tts
from voice.vad_detector import SileroVADDetector
from voice.wake_word import WakeWordDetector

__all__ = [
    "AudioStreamRecorder",
    "DictationManager",
    "SileroVADDetector",
    "TTSEngine",
    "VoiceListener",
    "WakeWordDetector",
    "dictation_manager",
    "tts",
]
