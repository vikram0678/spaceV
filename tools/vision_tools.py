"""
Screen Vision and Active Window Inspector for SpaceV.
Allows SpaceV to perceive what is on your screen and read the clipboard.
"""
import os
import ctypes
from pathlib import Path
from config import USER_DESKTOP_DIR

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_PYPERCLIP = True
except Exception:
    HAS_PYPERCLIP = False

def get_active_window_info() -> str:
    """
    Returns the title and process of the currently focused/active window on Windows.
    """
    try:
        title = ""
        if hasattr(ctypes, "windll"):
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            length = user32.GetWindowTextLengthW(hwnd)
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value.strip()

        screen_w, screen_h = pyautogui.size() if HAS_PYAUTOGUI else (1920, 1080)

        if title:
            return f"Active Window: '{title}' (Screen Resolution: {screen_w}x{screen_h})"
        return f"Desktop / Windows Shell (Resolution: {screen_w}x{screen_h})"
    except Exception as e:
        return f"Failed to get active window: {str(e)}"

def take_screen_snapshot(filename: str = "spacev_snapshot.png") -> str:
    """
    Takes a hardware-accelerated snapshot of your full Windows screen and saves it to your Desktop.
    """
    try:
        from core.screen_capture import capture_desktop_pil, get_active_capture_tier
        target_path = USER_DESKTOP_DIR / filename
        screenshot = capture_desktop_pil()
        if screenshot is None:
            return "Unable to capture desktop display."
        screenshot.save(str(target_path))
        tier = get_active_capture_tier()
        return f"Captured full screen snapshot via {tier} and saved to: {target_path}"
    except Exception as e:
        return f"Failed to capture screen: {str(e)}"

def read_clipboard_text() -> str:
    """
    Reads the text or code currently copied to the Windows clipboard with resilient retry.
    """
    import time
    for attempt in range(4):
        try:
            text = pyperclip.paste().strip()
            if not text:
                return "Windows clipboard is currently empty."
            preview = text[:400] + ("..." if len(text) > 400 else "")
            return f"Clipboard Content ({len(text)} chars):\n\n```\n{preview}\n```"
        except Exception:
            time.sleep(0.05 * (attempt + 1))
    return "Windows clipboard is currently empty."

def write_clipboard_text(text: str) -> str:
    """
    Copies specified text, code, or link directly into the Windows clipboard with resilient retry.
    """
    import time
    last_err = None
    for attempt in range(4):
        try:
            pyperclip.copy(text)
            return f"Successfully copied {len(text)} characters to your Windows clipboard, Sir."
        except Exception as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))
    return f"Failed to copy to clipboard: {str(last_err)}"

