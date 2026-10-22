"""
Main Entry Point for SpaceV Cybernetic Desktop AI Agent.
"""
import sys
import os
from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt

from config import APP_NAME, PRIMARY_MODEL
from core.ollama_client import OllamaAgent
from core.hotkey_listener import GlobalHotkeyListener
from ui.floating_icon import FloatingIcon
from ui.chat_window import ChatWindow
from ui.audio_effects import play_startup_sound

def create_tray_pixmap():
    """Generates a neat circular tray icon."""
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    painter.setBrush(QColor("#0d1117"))
    painter.setPen(QColor("#00f0ff"))
    painter.drawEllipse(2, 2, 28, 28)
    
    painter.setPen(QColor("#00f0ff"))
    font = QFont("Segoe UI", 12, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(0, 0, 32, 32, Qt.AlignmentFlag.AlignCenter, "⚡")
    painter.end()
    return pixmap

def main():
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    print(f"Starting {APP_NAME} powered by Ollama ({PRIMARY_MODEL})...")
    agent = OllamaAgent()

    # Initialize widgets
    floating_icon = FloatingIcon()
    chat_window = ChatWindow(agent)

    # Sync Arc Reactor visual state with chat window
    chat_window.state_changed.connect(floating_icon.set_state)

    # Pre-warm local Whisper STT engine in background for instant speech turn-taking
    from voice.stt_engine import OfflineWhisperSingleton
    OfflineWhisperSingleton.warm_up_in_background()

    def toggle_chat():
        from voice.frame_pipeline import frame_pipeline
        from voice.tts_engine import tts
        if tts.is_speaking:
            frame_pipeline.interrupt(reason="reactor_tap_barge_in")
        if chat_window.isVisible():
            chat_window.hide()
        else:
            chat_window.dock_near(floating_icon.pos())
            chat_window.show()
            chat_window.raise_()
            chat_window.activateWindow()

    _is_exiting = False

    def clean_exit():
        nonlocal _is_exiting
        if _is_exiting:
            return
        _is_exiting = True

        print(f"\n[SpaceV] Shutting down cleanly... (No background tasks lingering)")
        try:
            hotkey_listener.stop()
        except Exception:
            pass
        try:
            chat_window.cleanup()
        except Exception:
            pass
        try:
            app.quit()
        except Exception:
            pass
        os._exit(0)

    import atexit
    atexit.register(clean_exit)
    app.aboutToQuit.connect(clean_exit)

    floating_icon.clicked.connect(toggle_chat)
    floating_icon.clear_chat_requested.connect(chat_window.clear_conversation)
    floating_icon.exit_requested.connect(clean_exit)

    # Global Hotkey (Ctrl + Space)
    hotkey_listener = GlobalHotkeyListener()
    hotkey_listener.toggle_requested.connect(toggle_chat)

    # Play futuristic startup chime
    play_startup_sound()

    # Windows System Tray
    tray_icon = QSystemTrayIcon(QIcon(create_tray_pixmap()), app)
    tray_menu = QMenu()
    
    action_toggle = tray_menu.addAction(f"💬 Toggle {APP_NAME}")
    action_toggle.triggered.connect(toggle_chat)

    action_reset = tray_menu.addAction("📍 Reset Icon Position")
    action_reset.triggered.connect(floating_icon.init_position)

    tray_menu.addSeparator()

    action_quit = tray_menu.addAction(f"❌ Exit {APP_NAME}")
    action_quit.triggered.connect(clean_exit)

    tray_icon.setContextMenu(tray_menu)
    tray_icon.activated.connect(lambda reason: toggle_chat() if reason == QSystemTrayIcon.ActivationReason.Trigger else None)
    tray_icon.show()

    # Show floating icon initially
    floating_icon.show()

    # Proactive Vocal Startup Greeting ("Hello Sir, this is SpaceV...")
    def _proactive_startup():
        try:
            chat_window.dock_near(floating_icon.pos())
            chat_window.show()
            chat_window.raise_()
            chat_window.activateWindow()
            chat_window.play_initial_greeting()
        except Exception as e:
            print(f"[SpaceV] Startup greeting notice: {e}")

    # Handle Ctrl + C and termination signals cleanly in PyQt6
    import signal
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(1200, _proactive_startup)

    signal.signal(signal.SIGINT, lambda *_: clean_exit())
    try:
        signal.signal(signal.SIGTERM, lambda *_: clean_exit())
    except Exception:
        pass

    # Windows Console Close Event Handler (terminates immediately when terminal X is clicked)
    try:
        import win32api
        def _console_ctrl_handler(ctrl_type):
            clean_exit()
            return True
        win32api.SetConsoleCtrlHandler(_console_ctrl_handler, True)
    except Exception:
        pass

    sigint_timer = QTimer()
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start(250)

    print(f"{APP_NAME} Cybernetic Agent is online! Look for the glowing Arc Reactor on your screen.")
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
