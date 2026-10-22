"""
Standalone Live Microphone & Dictation Verification Tool for SpaceV.
Run this directly in terminal:
  .\\venv\\Scripts\\python.exe test_mic_live.py

Allows you to speak into your microphone and immediately verifies:
1. Microphone hardware connectivity and live volume levels (RMS).
2. Neural Silero VAD speech detection (turn onset & offset).
3. Local Faster-Whisper offline transcription ($0.00, zero cloud latency).
4. Direct keystroke / clipboard text injection into the active application.
"""
import sys
import time

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import pyaudio

from voice.audio_stream import AudioStreamRecorder
from voice.dictation_manager import DictationManager
from voice.stt_engine import OfflineWhisperSingleton, VoiceListener
from voice.vad_detector import SileroVADDetector


def main():
    print("=" * 65)
    print("  🎙️ SPACEV LIVE MICROPHONE & SPEECH-TO-TEXT VERIFIER 🎙️")
    print("=" * 65)

    # 1. Enumerate Audio Input Devices
    p = pyaudio.PyAudio()
    info = p.get_default_input_device_info()
    print(f"\n[AUDIO HARDWARE] Default Input Device: {info['name']}")
    print(f"                 Channels: {info['maxInputChannels']}, Default SR: {int(info['defaultSampleRate'])} Hz")
    p.terminate()

    # 2. Initialize VAD & Faster-Whisper
    print("\n[AI ENGINES] Initializing Neural Silero VAD (ONNX) + Faster-Whisper (int8)...")
    vad = SileroVADDetector()
    assert vad.is_neural, "Silero VAD failed to initialize!"
    whisper_model = OfflineWhisperSingleton.get_model()
    assert whisper_model is not None, "Faster-Whisper model failed to load!"
    print(" -> Both AI models loaded into RAM successfully!")

    # 3. Live Speech Test
    recorder = AudioStreamRecorder(vad=vad)
    print("\n" + "=" * 65)
    print("🔴 GET READY: Please SPEAK into your microphone now...")
    print("   Say anything (e.g. 'Hello SpaceV, testing live dictation')")
    print("=" * 65)

    pcm_data = recorder.record_utterance(timeout=7.0, phrase_limit=15.0)

    if not pcm_data:
        print("\n⚠️ No speech detected (Microphone timed out after 7s of silence).")
        print("Tip: Check Windows Microphone permissions or microphone volume settings.")
        return

    print(f"\n[MIC SUCCESS] Captured {len(pcm_data)} bytes of speech audio (~{len(pcm_data)/32000:.2f}s)!")
    print("[AI TRANSCRIBING] Converting speech to text via local Faster-Whisper...")

    t0 = time.time()
    transcribed_text = VoiceListener.transcribe_pcm(pcm_data).strip()
    elapsed = time.time() - t0

    print("\n" + "=" * 65)
    print(f"✨ RESULT TRANSCRIBED ({elapsed:.2f}s latency):")
    print(f"👉 \"{transcribed_text}\"")
    print("=" * 65)

    if transcribed_text:
        print("\n[INJECTION TEST] Injecting text into your active window in 3 seconds...")
        print("Switch focus to Notepad or your chat now if desired!")
        time.sleep(3)
        DictationManager.inject_text_into_active_window(transcribed_text)
        print("✅ Text injected via Ctrl+V clipboard bridge!")

if __name__ == "__main__":
    main()
