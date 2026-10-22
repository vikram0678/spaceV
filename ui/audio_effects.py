"""
Futuristic Sci-Fi Audio Chimes and Sound Effects for SpaceV.
Uses native Windows sound synthesis (winsound) on background threads with zero extra dependencies.
"""
try:
    import winsound
except ImportError:
    winsound = None

# import winsound
import threading
import time

def _play_async(fn):
    if not winsound:
        return
    threading.Thread(target=fn, daemon=True).start()

def play_startup_sound():
    """Futuristic rising 3-tone startup chime."""
    def _run():
        try:
            tones = [(523, 70), (659, 70), (784, 90), (1046, 140)]
            for freq, dur in tones:
                winsound.Beep(freq, dur)
                time.sleep(0.02)
        except Exception:
            pass
    _play_async(_run)

def play_listening_sound():
    """Soft ready chime when microphone activates."""
    def _run():
        try:
            winsound.Beep(880, 80)
            winsound.Beep(1174, 100)
        except Exception:
            pass
    _play_async(_run)

def play_action_sound():
    """Crisp confirmation chirp when an action executes."""
    def _run():
        try:
            winsound.Beep(1046, 60)
            winsound.Beep(1318, 80)
        except Exception:
            pass
    _play_async(_run)

def play_emergency_sound():
    """Alert drop tone when emergency stop or abort is triggered."""
    def _run():
        try:
            winsound.Beep(600, 100)
            winsound.Beep(300, 150)
        except Exception:
            pass
    _play_async(_run)
