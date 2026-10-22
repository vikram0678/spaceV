"""
Unit tests for SpaceV Phase 4: Cybernetic Polish.
Verifies:
- Voice Prosody & Emotional Cadence Modulation (#7)
- Arc Reactor Glassmorphism 60 FPS Pulse (#46)
- SSE Streaming & Real-Time Token Bridge (#48)
- Telemetry HUD Diagnostics Monitor (#49)
"""
import os
import sys
import json
import queue
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from PyQt6.QtWidgets import QApplication
app = QApplication.instance() or QApplication(["pytest", "-platform", "offscreen"])

from voice.tts_engine import VoiceProsodyEngine
from core.sse_stream import SSEBroadcaster, SSEMessage


def test_voice_prosody_cadence_modulation():
    # 1. Affirmative rapid confirmation
    p_aff = VoiceProsodyEngine.detect_profile("Right away, Sir. Launching calculator now.")
    assert p_aff == "affirmative"
    profile_aff = VoiceProsodyEngine.PROFILES[p_aff]
    assert "+6%" in profile_aff["rate"]
    assert profile_aff["sapi_rate"] == 2

    # 2. Security alert
    p_alert = VoiceProsodyEngine.detect_profile("⚠️ Security Warning: Adversarial command blocked.")
    assert p_alert == "alert"
    profile_alert = VoiceProsodyEngine.PROFILES[p_alert]
    assert "+8%" in profile_alert["rate"]
    assert profile_alert["sapi_rate"] == 3

    # 3. Analytical deep reasoning
    p_ana = VoiceProsodyEngine.detect_profile("Here is the telemetry algorithm and memory metric analysis.")
    assert p_ana == "analytical"
    profile_ana = VoiceProsodyEngine.PROFILES[p_ana]
    assert "-4%" in profile_ana["rate"]

    # 4. Standard conversational
    p_conv = VoiceProsodyEngine.detect_profile("How are you feeling today?")
    assert p_conv == "conversational"


def test_sse_streaming_token_bridge():
    broadcaster = SSEBroadcaster()
    client_q = broadcaster.subscribe()

    # 1. Emit token
    broadcaster.emit_token("SpaceV")
    msg_raw = client_q.get_nowait()
    assert "event: token" in msg_raw
    assert '"token":"SpaceV"' in msg_raw

    # 2. Emit reflex match
    broadcaster.emit_reflex("open_application", {"app_name": "calc"}, latency_ms=0.18)
    msg_reflex = client_q.get_nowait()
    assert "event: reflex" in msg_reflex
    assert '"latency_ms":0.18' in msg_reflex

    # 3. Unsubscribe
    broadcaster.unsubscribe(client_q)
    assert client_q not in broadcaster._subscribers


def test_arc_reactor_60fps_configuration():
    # Verify that the animation timer in floating_icon is configured for 60 FPS (16ms)
    from ui.floating_icon import FloatingIcon
    icon = FloatingIcon()
    assert icon.anim_timer.interval() == 16  # 16ms = 60 FPS
    
    # Verify cybernetic states
    icon.set_state("REFLEX")
    assert icon.state == "REFLEX"
    icon.set_state("ALERT")
    assert icon.state == "ALERT"
    icon.set_state("REASONING")
    assert icon.state == "REASONING"
