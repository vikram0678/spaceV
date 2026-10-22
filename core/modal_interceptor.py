"""
Universal Modal Interceptor & Disambiguation Engine for SpaceV.
Provides OS-level detection of Gatekeeper Modals (profile selectors, trust prompts,
file conflict dialogs, and confirmation popups) across all Windows applications.
Follows the 4-layer Universal Decoupled Architecture.
"""
import ctypes
import re
import time
from dataclasses import dataclass

from core.memory import memory
from tools.vision_tools import get_active_window_info

try:
    import psutil
    import win32con
    import win32gui
    import win32process
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


@dataclass
class GatekeeperModal:
    is_active: bool
    domain: str                     # e.g., "chrome", "vscode", "notepad", "system", "file_explorer"
    dialog_title: str               # e.g., "Who's using Chrome?", "Confirm File Replace", "Trust Authors"
    property_key: str               # e.g., "profile", "overwrite_policy", "trust_mode"
    question: str                   # Clean Jarvis-grade question to ask the user
    options: list[tuple[str, str]]  # [("👤 n. vikram", "vikram"), ("👤 Vicky Space", "vicky")]
    default_option: str | None = None
    raw_window_info: str = ""


class UniversalModalInterceptor:
    """
    Universal closed-loop gatekeeper detection and resolution engine.
    Detects when an application presents an interactive decision fork,
    resolves from hierarchical memory if known, or halts safely to ask the user.
    """
    def __init__(self):
        pass

    def inspect_active_window(self) -> tuple[str, str, str]:
        """
        Returns (window_title, process_name, class_name) for the currently focused window.
        """
        win_info = get_active_window_info()
        title = ""
        proc_name = "unknown"
        cls_name = ""

        # Extract title from get_active_window_info() preview
        m = re.search(r"Active Window:\s*'([^']*)'", win_info)
        if m:
            title = m.group(1).strip()

        if HAS_WIN32:
            try:
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd and win32gui.IsWindow(hwnd):
                    if not title:
                        title = win32gui.GetWindowText(hwnd).strip()
                    cls_name = win32gui.GetClassName(hwnd)
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    if pid:
                        try:
                            proc_name = psutil.Process(pid).name().lower().replace(".exe", "")
                        except Exception:
                            pass
            except Exception:
                pass

        if not proc_name or proc_name == "unknown":
            title_lower = title.lower()
            if "chrome" in title_lower:
                proc_name = "chrome"
            elif "code" in title_lower or "visual studio code" in title_lower:
                proc_name = "vscode"
            elif "notepad" in title_lower:
                proc_name = "notepad"
            elif "explorer" in title_lower or "file" in title_lower:
                proc_name = "file_explorer"
            else:
                proc_name = "system"

        return title, proc_name, cls_name

    def detect(self) -> GatekeeperModal | None:
        """
        Inspects the desktop to detect any blocking gatekeeper modal across all applications.
        """
        title, domain, cls_name = self.inspect_active_window()
        title_lower = title.lower()

        # 1. Chrome / Browser Multi-Profile Selector
        if "who's using chrome" in title_lower or ("chrome" in title_lower and ("profile" in title_lower or "who" in title_lower)):
            return GatekeeperModal(
                is_active=True,
                domain="chrome",
                dialog_title=title or "Who's using Chrome?",
                property_key="profile",
                question=(
                    "Sir, Chrome is waiting on the profile selection screen ('Who's using Chrome?'). "
                    "Which profile shall I open for you: **'n. vikram'** or **'Vicky Space'**?"
                ),
                options=[
                    ("👤 n. vikram", "vikram"),
                    ("👤 Vicky Space", "vicky")
                ],
                default_option="vikram",
                raw_window_info=title
            )

        # 2. File Conflict / Replace Modal
        if any(k in title_lower for k in ["replace or skip", "destination already has", "file exists", "confirm file replace"]):
            return GatekeeperModal(
                is_active=True,
                domain="file_explorer",
                dialog_title=title,
                property_key="conflict_policy",
                question="Sir, a file conflict occurred. Would you like me to replace the destination file, skip it, or keep both?",
                options=[
                    ("🔄 Replace", "replace"),
                    ("⏭️ Skip", "skip"),
                    ("📄 Keep Both", "keep_both")
                ],
                default_option="replace",
                raw_window_info=title
            )

        # 3. Unsaved Changes Confirmation Dialog
        if any(k in title_lower for k in ["save changes", "do you want to save", "confirm exit", "unsaved changes"]) or (
            cls_name == "#32770" and "save" in title_lower
        ):
            return GatekeeperModal(
                is_active=True,
                domain=domain,
                dialog_title=title,
                property_key="unsaved_action",
                question=f"Sir, {domain.capitalize()} is asking whether to save unsaved changes. What would you like me to do?",
                options=[
                    ("💾 Save", "save"),
                    ("❌ Don't Save", "dont_save"),
                    ("↩️ Cancel", "cancel")
                ],
                default_option="save",
                raw_window_info=title
            )

        # 4. Security / Trust Prompt (VS Code / Windows)
        if any(k in title_lower for k in ["trust this workspace", "trust authors", "security warning", "open file - security"]):
            return GatekeeperModal(
                is_active=True,
                domain=domain,
                dialog_title=title,
                property_key="trust_mode",
                question=f"Sir, {domain.capitalize()} is prompting for workspace security trust. Shall I trust this workspace?",
                options=[
                    ("🛡️ Trust Workspace", "trust"),
                    ("⛔ Deny", "deny")
                ],
                default_option="trust",
                raw_window_info=title
            )

        # 5. Generic Win32 Dialog Box (#32770 or WS_DLGFRAME)
        if cls_name == "#32770" and title:
            # Check for child buttons if Win32 is available
            buttons = self._get_dialog_buttons()
            if buttons and len(buttons) >= 2:
                opts = [(f"🔘 {b}", b.lower()) for b in buttons[:3]]
                return GatekeeperModal(
                    is_active=True,
                    domain=domain,
                    dialog_title=title,
                    property_key="dialog_response",
                    question=f"Sir, {title} is requesting user confirmation. How would you like me to proceed?",
                    options=opts,
                    default_option=opts[0][1] if opts else None,
                    raw_window_info=title
                )

        return None

    def _get_dialog_buttons(self) -> list[str]:
        """Extracts text of child push buttons in a Win32 dialog."""
        buttons = []
        if not HAS_WIN32:
            return buttons

        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd or not win32gui.IsWindow(hwnd):
                return buttons

            def enum_child_cb(child_hwnd, _):
                cls = win32gui.GetClassName(child_hwnd)
                if cls.lower() == "button":
                    txt = win32gui.GetWindowText(child_hwnd).strip()
                    if txt and len(txt) <= 25 and not txt.isdigit():
                        buttons.append(txt)
                return True

            win32gui.EnumChildWindows(hwnd, enum_child_cb, None)
        except Exception:
            pass

        return buttons

    def resolve_or_intercept(self, pending_task: str | None = None) -> tuple[bool, GatekeeperModal | None, str]:
        """
        Universal closed-loop gatekeeper handler:
        1. Checks if any gatekeeper modal is active.
        2. If none, returns (True, None, 'Clear').
        3. If detected, checks memory for user preference.
           - If preference exists: auto-executes resolution keystroke and verifies.
           - If preference does not exist: stores suspended disambiguation and halts.
        """
        gatekeeper = self.detect()
        if not gatekeeper:
            return True, None, "Clear"

        pref = memory.get_preference(gatekeeper.domain, gatekeeper.property_key)

        # If preference exists in hierarchical memory, auto-resolve!
        if pref:
            pref_str = str(pref).lower()
            print(f"  [INTERCEPTOR] 🛡️ Auto-resolving gatekeeper modal: {gatekeeper.domain}.{gatekeeper.property_key}='{pref_str}'...")

            import pyautogui
            if gatekeeper.domain == "chrome" and gatekeeper.property_key == "profile":
                if "vicky" in pref_str or "space" in pref_str or "2" in pref_str:
                    pyautogui.press("right")
                    time.sleep(0.15)
                pyautogui.press("enter")
                time.sleep(1.5)

            elif gatekeeper.domain == "file_explorer":
                if "replace" in pref_str:
                    pyautogui.press("enter")
                elif "skip" in pref_str:
                    pyautogui.press("esc")
                time.sleep(0.5)

            elif "save" in gatekeeper.property_key:
                if "dont" in pref_str:
                    pyautogui.hotkey("alt", "n")
                elif "save" in pref_str:
                    pyautogui.hotkey("alt", "s")
                    pyautogui.press("enter")
                time.sleep(0.5)

            else:
                pyautogui.press("enter")
                time.sleep(0.5)

            # Verify if modal cleared
            post_title, _, _ = self.inspect_active_window()
            if gatekeeper.dialog_title.lower() in post_title.lower():
                # Modal did not clear; suspend and ask user
                memory.set_suspended_disambiguation({
                    "domain": gatekeeper.domain,
                    "property_key": gatekeeper.property_key,
                    "question": gatekeeper.question,
                    "options": gatekeeper.options,
                    "suspended_task": pending_task,
                    "timestamp": time.time()
                })
                return False, gatekeeper, f"Modal '{gatekeeper.dialog_title}' remained stuck after resolution attempt."

            return True, gatekeeper, f"Auto-resolved {gatekeeper.domain}.{gatekeeper.property_key}='{pref_str}'"

        # No preference found: suspend execution & prepare clarification for user
        memory.set_suspended_disambiguation({
            "domain": gatekeeper.domain,
            "property_key": gatekeeper.property_key,
            "question": gatekeeper.question,
            "options": gatekeeper.options,
            "suspended_task": pending_task,
            "timestamp": time.time()
        })

        return False, gatekeeper, gatekeeper.question


modal_interceptor = UniversalModalInterceptor()
