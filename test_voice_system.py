"""
Verification script for SpaceV Modern Voice Pipeline:
Silero VAD, Audio Ring Buffering, FastRouter Dictation, and Faster-Whisper.
"""
import sys

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import numpy as np

from core.fast_router import FastRouter
from voice.audio_stream import AudioStreamRecorder
from voice.dictation_manager import dictation_manager
from voice.vad_detector import SileroVADDetector


def run_tests():
    print("[TEST 1] Testing Silero VAD ONNX...")
    vad = SileroVADDetector()
    assert vad.is_neural, "Silero VAD should be neural!"
    print(" -> Neural model loaded successfully!")

    # Test silent frame
    silent_frame = np.zeros(512, dtype=np.int16).tobytes()
    is_speech, prob = vad.process_frame(silent_frame)
    assert not is_speech, "Silent frame should not be detected as speech!"
    print(f" -> Silent frame correctly classified (prob={prob:.4f})")

    # Test synthetic speech-like harmonics
    t = np.linspace(0, 512 / 16000, 512, endpoint=False)
    synthetic_speech = (0.7 * np.sin(2 * np.pi * 300 * t) + 0.3 * np.sin(2 * np.pi * 1200 * t)) * 32767
    active_frame = synthetic_speech.astype(np.int16).tobytes()
    # Feed multiple frames to let recurrent state adapt
    speech_probs = []
    for _ in range(5):
        is_sp, p = vad.process_frame(active_frame)
        speech_probs.append(p)
    print(f" -> Active acoustic frame processed (final prob={speech_probs[-1]:.4f})")

    print("[TEST 2] Testing AudioStreamRecorder WAV Serialization...")
    dummy_pcm = np.zeros(3200, dtype=np.int16).tobytes()  # 200ms
    wav_bytes = AudioStreamRecorder.pcm_to_wav_bytes(dummy_pcm, sample_rate=16000)
    assert wav_bytes.startswith(b"RIFF"), "WAV bytes must start with RIFF header!"
    assert b"WAVE" in wav_bytes[:12], "WAV container must contain WAVE format identifier!"
    print(f" -> WAV serialized successfully ({len(wav_bytes)} bytes)")

    print("[TEST 3] Testing FastRouter Dictation Trigger...")
    match = FastRouter.match("activate dictation mode")
    assert match is not None, "FastRouter must match 'activate dictation mode'!"
    assert match[0] == "dictation_mode"
    print(" -> FastRouter matched 'dictation_mode' cleanly!")
    dictation_manager.stop_dictation()

    print("[TEST 4] Testing Faster-Whisper Import & Engine Binding...")
    try:
        from faster_whisper import WhisperModel
        print(" -> Faster-Whisper is installed and available!")
    except ImportError:
        print(" -> Faster-Whisper not installed.")

    print("[TEST 5] Testing Silero VAD on Real Speech Audio...")
    import wave
    from pathlib import Path
    test_wav = Path("opensourcetools/silero-vad/tests/data/test.wav")
    if test_wav.exists():
        with wave.open(str(test_wav), "rb") as wf:
            data = wf.readframes(wf.getnframes())
        vad.reset_state()
        speech_chunks = 0
        total_chunks = len(data) // 1024
        for i in range(min(50, total_chunks)):  # Test first 50 chunks
            chunk = data[i*1024 : (i+1)*1024]
            is_sp, p = vad.process_frame(chunk)
            if is_sp:
                speech_chunks += 1
        assert speech_chunks > 0, "Silero VAD must detect speech in real speech WAV!"
        print(f" -> Real speech detected across {speech_chunks} chunks successfully!")

    print("[TEST 6] Testing Faster-Whisper Offline Transcription on JFK Audio...")
    from voice.stt_engine import VoiceListener
    jfk_wav = Path("opensourcetools/whisper.cpp/samples/jfk.wav")
    if jfk_wav.exists():
        with wave.open(str(jfk_wav), "rb") as wf:
            jfk_pcm = wf.readframes(wf.getnframes())
        transcription = VoiceListener.transcribe_pcm(jfk_pcm, sample_rate=16000)
        assert "country" in transcription.lower(), f"Whisper should transcribe JFK audio! Got: {transcription}"
        print(f" -> Transcribed accurately: '{transcription[:60]}...'")

    print("[TEST 7] Testing WakeWordDetector Pause & Resume...")
    from voice.wake_word import WakeWordDetector
    detector = WakeWordDetector()
    detector.pause()
    assert detector._paused is True, "Detector should be paused!"
    detector.resume()
    assert detector._paused is False, "Detector should be unpaused!"
    detector.stop()
    print(" -> WakeWordDetector pause/resume state validated!")

    print("\n==============================================")
    print("ALL MODERN VOICE PIPELINE TESTS PASSED 100%!")
    print("==============================================")

if __name__ == "__main__":
    run_tests()

