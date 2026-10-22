"""
Desktop Dictation & Direct Text Injection Service for SpaceV.
Inspired by Handy (github.com/cjpais/Handy).
Allows the user to speak anywhere on Windows and automatically pastes transcribed text
directly into the active focused window (VS Code, Browser, Slack, Word, etc.).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Callable

try:
    import pyautogui
except Exception:
    class MockPyAutoGUI:
        @staticmethod
        def hotkey(*args, **kwargs): pass
        @staticmethod
        def typewrite(*args, **kwargs): pass
    pyautogui = MockPyAutoGUI()

try:
    import pyperclip
except Exception:
    class MockPyperclip:
        @staticmethod
        def copy(text): pass
        @staticmethod
        def paste(): return ""
    pyperclip = MockPyperclip()

from PyQt6.QtCore import QObject, pyqtSignal
from voice.stt_engine import VoiceListener

import sys
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

logger = logging.getLogger("SpaceV.Dictation")


class DictationManager(QObject):
    """
    Manages push-to-talk or voice-triggered OS dictation.
    Injects transcribed speech directly into whichever window has active focus.
    """
    dictation_started = pyqtSignal()
    dictation_finished = pyqtSignal(str)
    dictation_error = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._listener: Optional[VoiceListener] = None
        self._is_active = False

    def toggle_dictation(self, on_complete: Optional[Callable[[str], None]] = None) -> bool:
        """Toggles dictation mode on or off."""
        if self._is_active:
            self.stop_dictation()
            return False
        else:
            self.start_dictation(on_complete=on_complete)
            return True

    def start_dictation(self, on_complete: Optional[Callable[[str], None]] = None, auto_start_listener: bool = True) -> None:
        """Starts listening for dictation."""
        if self._is_active:
            return

        self._is_active = True
        self.dictation_started.emit()

        if auto_start_listener:
            self._listener = VoiceListener(timeout=5.0, phrase_limit=15.0)
            self._listener.speech_recognized.connect(lambda text: self._on_transcribed(text, on_complete))
            self._listener.error_occurred.connect(self._on_error)
            self._listener.listening_finished.connect(self._on_finished)
            self._listener.start()
        print("[Dictation] [OK] Dictation active. Speak your text...")

    def stop_dictation(self) -> None:
        """Aborts active dictation."""
        if self._listener:
            self._listener.stop()
            self._listener = None
        self._is_active = False

    def _on_transcribed(self, text: str, callback: Optional[Callable[[str], None]]) -> None:
        if not text:
            return

        print(f"[Dictation] ⚡ Injecting text: '{text}' into active window...")
        self.inject_text_into_active_window(text)
        self.dictation_finished.emit(text)
        if callback:
            try:
                callback(text)
            except Exception as e:
                logger.debug(f"[Dictation] Callback error: {e}")

    def _on_error(self, err: str) -> None:
        logger.debug(f"[Dictation] Error: {err}")
        self.dictation_error.emit(err)

    def _on_finished(self) -> None:
        self._is_active = False
        self._listener = None

    @staticmethod
    def inject_text_into_active_window(text: str) -> None:
        """
        Safely injects text into the active Windows application using the clipboard bridge.
        Preserves original clipboard contents by restoring them after a brief delay.
        """
        def _worker():
            try:
                # 1. Backup existing clipboard content
                try:
                    original_clipboard = pyperclip.paste()
                except Exception:
                    original_clipboard = ""

                # 2. Put transcribed text into clipboard
                pyperclip.copy(text)
                time.sleep(0.05)

                # 3. Simulate Ctrl + V paste into active window
                pyautogui.hotkey("ctrl", "v")
                time.sleep(0.2)

                # 4. Restore original clipboard content
                try:
                    pyperclip.copy(original_clipboard)
                except Exception:
                    pass

            except Exception as e:
                logger.error(f"[Dictation] Failed to inject text into window: {e}")

        # Run clipboard injection in a separate brief thread to avoid blocking GUI
        threading.Thread(target=_worker, daemon=True).start()


# Global Singleton Instance
dictation_manager = DictationManager()
