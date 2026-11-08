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


def get_detected_chrome_profiles() -> list[dict[str, str]]:
    """
    Reads Chrome's Local State to retrieve all configured user profiles.
    Returns list of dicts with id, name, gaia_name, email, display.
    """
    import json, os, sys
    paths = []
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            paths.append(os.path.join(local_app, "Google", "Chrome", "User Data", "Local State"))
    user = os.environ.get("USERNAME", os.environ.get("USER", ""))
    if user:
        for drive in ["C:", "/mnt/c"]:
            paths.append(f"{drive}/Users/{user}/AppData/Local/Google/Chrome/User Data/Local State")

    for p in paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                info = data.get("profile", {}).get("info_cache", {})
                profiles = []
                for prof_id, meta in info.items():
                    name = meta.get("name", prof_id)
                    gaia_name = meta.get("gaia_name", "")
                    user_name = meta.get("user_name", "")
                    disp = gaia_name or name
                    if name and name != disp and name not in disp:
                        disp = f"{disp} ({name})"
                    profiles.append({
                        "id": prof_id,
                        "name": name,
                        "gaia_name": gaia_name,
                        "email": user_name,
                        "display": disp,
                    })
                if profiles:
                    return profiles
            except Exception:
                pass
    return []


@dataclass
class GatekeeperModal:
    is_active: bool
    domain: str                     # e.g., "chrome", "vscode", "notepad", "system", "file_explorer"
    dialog_title: str               # e.g., "Who's using Chrome?", "Confirm File Replace", "Trust Authors"
    property_key: str               # e.g., "profile", "overwrite_policy", "trust_mode"
    question: str                   # Clean Jarvis-grade question to ask the user
    options: list[tuple[str, str]]  # [(label, value)]
    default_option: str | None = None
    raw_window_info: str = ""
    hwnd: int | None = None
    window_rect: tuple[int, int, int, int] | None = None  # (x, y, w, h)


class UniversalModalInterceptor:
    """
    Universal closed-loop gatekeeper detection and resolution engine.
    Detects when an application presents an interactive decision fork,
    resolves from hierarchical memory if known, or halts safely to ask the user.
    """
    def __init__(self):
        self.last_hwnd: int | None = None
        self.last_rect: tuple[int, int, int, int] | None = None

    def inspect_active_window(self) -> tuple[str, str, str]:
        """
        Returns (window_title, process_name, class_name) for the currently focused window,
        caching HWND and bounding box geometry.
        """
        win_info = get_active_window_info()
        title = ""
        proc_name = "unknown"
        cls_name = ""
        self.last_hwnd = None
        self.last_rect = None

        # Extract title from get_active_window_info() preview
        m = re.search(r"Active Window:\s*'([^']*)'", win_info)
        if m:
            title = m.group(1).strip()

        if HAS_WIN32:
            try:
                user32 = ctypes.windll.user32
                hwnd = user32.GetForegroundWindow()
                if hwnd and win32gui.IsWindow(hwnd):
                    self.last_hwnd = hwnd
                    if not title:
                        title = win32gui.GetWindowText(hwnd).strip()
                    cls_name = win32gui.GetClassName(hwnd)
                    try:
                        l, t, r, b = win32gui.GetWindowRect(hwnd)
                        self.last_rect = (l, t, max(1, r - l), max(1, b - t))
                    except Exception:
                        pass
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

    def _get_dialog_text_and_buttons(self, hwnd: int | None = None) -> tuple[str, list[str]]:
        """
        Dynamically extracts static label text and push buttons from any Win32 or modern dialog.
        """
        target_hwnd = hwnd or self.last_hwnd
        texts: list[str] = []
        buttons: list[str] = []

        if not HAS_WIN32 or not target_hwnd:
            return "", buttons

        try:
            def enum_child_cb(child_hwnd, _):
                try:
                    cls = win32gui.GetClassName(child_hwnd).lower()
                    txt = win32gui.GetWindowText(child_hwnd).strip()
                    if not txt:
                        return True
                    if "button" in cls:
                        if len(txt) <= 30 and not txt.isdigit():
                            if txt not in buttons:
                                buttons.append(txt)
                    elif "static" in cls:
                        if len(txt) > 1 and not txt.startswith("Icon_"):
                            texts.append(txt)
                except Exception:
                    pass
                return True

            win32gui.EnumChildWindows(target_hwnd, enum_child_cb, None)
        except Exception:
            pass

        # Fallback to UI Automation controls if Win32 button enumeration yielded nothing
        if not buttons:
            try:
                from core.uia_grounding import list_interactive_controls
                uia_ctrls = list_interactive_controls(target_hwnd, limit=8)
                for c in uia_ctrls:
                    name = c.get("name", "").strip()
                    c_type = c.get("type", "").lower()
                    if name and ("button" in c_type or "item" in c_type or len(name) <= 25):
                        if name not in buttons:
                            buttons.append(name)
            except Exception:
                pass

        prompt_text = " ".join(texts).strip()
        return prompt_text, buttons

    def detect(self) -> GatekeeperModal | None:
        """
        Inspects the desktop to detect any blocking gatekeeper modal across all applications.
        Follows the strict rule: Ask ONLY when genuinely confused or blocked.
        Silent execution when clear.
        """
        title, domain, cls_name = self.inspect_active_window()
        title_lower = title.lower()

        # 1. Chrome / Browser Multi-Profile Selector
        # Triggers whenever the profile selection screen is explicitly active
        profiles = get_detected_chrome_profiles()
        is_chrome = domain == "chrome" or "chrome" in title_lower
        is_profile_picker = (
            "who's using chrome" in title_lower
            or "who is using chrome" in title_lower
            or (is_chrome and ("who's using" in title_lower or "profile picker" in title_lower))
        )

        # Physical Roadblock Check: If the profile picker is physically active on screen
        # and multiple profiles exist on the host machine, detect the roadblock unconditionally!
        if is_profile_picker and len(profiles) > 1:
            options = []
            q_lines = [
                "Sir, Chrome is waiting on the profile selection screen ('Who's using Chrome?').",
                "Which profile would you like me to use?"
            ]
            for idx, p in enumerate(profiles, 1):
                options.append((f"👤 {p['display']}", p["id"]))
                q_lines.append(f"{idx}. 👤 {p['display']}" + (f" ({p['email']})" if p.get('email') else ""))

            if not options:
                options = [("👤 Default Profile", "Default")]
                q_lines.append("1. 👤 Default Profile")

            question = "\n".join(q_lines)
            return GatekeeperModal(
                is_active=True,
                domain="chrome",
                dialog_title=title or "Who's using Chrome?",
                property_key="profile",
                question=question,
                options=options,
                default_option=options[0][1] if options else "Default",
                raw_window_info=title,
                hwnd=self.last_hwnd,
                window_rect=self.last_rect
            )

        # 2. File Conflict / Replace / File in Use Modal (Windows File Explorer / Shell)
        if any(k in title_lower for k in ["replace or skip", "destination already has", "file exists", "confirm file replace", "confirm folder replace", "file in use"]):
            return GatekeeperModal(
                is_active=True,
                domain="file_explorer",
                dialog_title=title or "File Conflict",
                property_key="conflict_policy",
                question="Sir, a file conflict occurred. Would you like me to replace the destination file, skip it, or keep both?",
                options=[
                    ("🔄 Replace", "replace"),
                    ("⏭️ Skip", "skip"),
                    ("📄 Keep Both", "keep_both")
                ],
                default_option="replace",
                raw_window_info=title,
                hwnd=self.last_hwnd,
                window_rect=self.last_rect
            )

        # 3. Unsaved Changes Confirmation Dialog (Notepad, VS Code, Word, Paint, etc.)
        if any(k in title_lower for k in ["save changes", "do you want to save", "confirm exit", "unsaved changes"]) or (
            cls_name == "#32770" and "save" in title_lower
        ):
            return GatekeeperModal(
                is_active=True,
                domain=domain,
                dialog_title=title or "Unsaved Changes",
                property_key="unsaved_action",
                question=f"Sir, {domain.capitalize()} is asking whether to save unsaved changes. What would you like me to do?",
                options=[
                    ("💾 Save", "save"),
                    ("❌ Don't Save", "dont_save"),
                    ("↩️ Cancel", "cancel")
                ],
                default_option="save",
                raw_window_info=title,
                hwnd=self.last_hwnd,
                window_rect=self.last_rect
            )

        # 4. Security / Trust Prompt (VS Code / Windows Defender / Security Warning)
        if any(k in title_lower for k in [
            "trust this workspace",
            "do you trust the authors",
            "security warning",
            "open file - security",
            "windows defender firewall",
            "user account control"
        ]):
            return GatekeeperModal(
                is_active=True,
                domain=domain,
                dialog_title=title or "Security Trust Prompt",
                property_key="trust_mode",
                question=f"Sir, {domain.capitalize()} is prompting for security trust authorization. Shall I allow this?",
                options=[
                    ("🛡️ Trust / Allow", "trust"),
                    ("⛔ Deny / Restrict", "deny")
                ],
                default_option="trust",
                raw_window_info=title,
                hwnd=self.last_hwnd,
                window_rect=self.last_rect
            )

        # 5. Generic Win32 Dialog Box (#32770 or WS_DLGFRAME)
        if cls_name == "#32770" and title:
            # Check for child buttons and text dynamically
            prompt_text, buttons = self._get_dialog_text_and_buttons(self.last_hwnd)
            if buttons and len(buttons) >= 2:
                opts = [(f"🔘 {b}", b.lower()) for b in buttons[:4]]
                summary_prompt = prompt_text[:120] if prompt_text else title
                return GatekeeperModal(
                    is_active=True,
                    domain=domain,
                    dialog_title=title,
                    property_key="dialog_response",
                    question=f"Sir, {title} is requesting confirmation: '{summary_prompt}'. How would you like me to proceed?",
                    options=opts,
                    default_option=opts[0][1] if opts else None,
                    raw_window_info=title,
                    hwnd=self.last_hwnd,
                    window_rect=self.last_rect
                )

        return None

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
        if not pref and gatekeeper.domain == "chrome":
            pref = memory.get("preferred_chrome_profile")

        # If preference exists in hierarchical memory, auto-resolve!
        if pref:
            from tools.gui_tools import safety
            if not safety.autonomous_mode_enabled:
                return False, gatekeeper, (
                    f"Modal '{gatekeeper.dialog_title}' needs a desktop action, but desktop control is off. "
                    "Please enable Desktop control or resolve the dialog yourself."
                )
            pref_str = str(pref).strip()
            print(f"  [INTERCEPTOR] 🛡️ Auto-resolving gatekeeper modal: {gatekeeper.domain}.{gatekeeper.property_key}='{pref_str}'...")

            import pyautogui
            if gatekeeper.domain == "chrome" and gatekeeper.property_key == "profile":
                from core.platform_adapter import PlatformAdapter
                profiles = get_detected_chrome_profiles()
                matched_p = next((p for p in profiles if p["id"] == pref_str or p["display"].lower() == pref_str.lower()), None)

                # Tier 1: Try clicking the profile card visually via UIA / OCR
                clicked = False
                if matched_p:
                    try:
                        from core.uia_grounding import gui_click_control
                        for t_name in [matched_p.get("gaia_name"), matched_p.get("name"), matched_p.get("display")]:
                            if t_name and "Autonomously located" in gui_click_control(t_name):
                                clicked = True
                                break
                    except Exception:
                        pass

                # Tier 2: Launch Chrome with explicit profile directory
                if not clicked:
                    PlatformAdapter.launch_app("chrome", profile_dir=pref_str)
                time.sleep(1.2)

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
                # Modal did not clear; project Holographic Visor amber HUD and ask user
                try:
                    from ui.holographic_visor import HolographicVisor
                    visor = HolographicVisor.get_instance()
                    if visor:
                        if hasattr(visor, "highlight_modal_elements"):
                            visor.highlight_modal_elements(gatekeeper.options, hwnd=self.last_hwnd, window_rect=gatekeeper.window_rect)
                        elif gatekeeper.window_rect:
                            gx, gy, gw, gh = gatekeeper.window_rect
                            visor.highlight_target(gx, gy, gw, gh, label=f"ROADBLOCK: {gatekeeper.domain.upper()}", duration_ms=25000)
                        visor.set_attention(f"Roadblock detected: {gatekeeper.dialog_title}")
                except Exception:
                    pass

                memory.set_suspended_disambiguation({
                    "domain": gatekeeper.domain,
                    "property_key": gatekeeper.property_key,
                    "question": gatekeeper.question,
                    "options": gatekeeper.options,
                    "suspended_task": pending_task,
                    "timestamp": time.time()
                })
                return False, gatekeeper, f"Modal '{gatekeeper.dialog_title}' remained stuck after resolution attempt. Please choose an option."

            return True, gatekeeper, f"Auto-resolved {gatekeeper.domain}.{gatekeeper.property_key}='{pref_str}'"

        # No preference found: project Holographic Visor amber reticles & suspend execution
        try:
            from ui.holographic_visor import HolographicVisor
            visor = HolographicVisor.get_instance()
            if visor:
                if hasattr(visor, "highlight_modal_elements"):
                    visor.highlight_modal_elements(gatekeeper.options, hwnd=self.last_hwnd, window_rect=gatekeeper.window_rect)
                elif gatekeeper.window_rect:
                    gx, gy, gw, gh = gatekeeper.window_rect
                    visor.highlight_target(gx, gy, gw, gh, label=f"ROADBLOCK: {gatekeeper.domain.upper()}", duration_ms=25000)
                visor.set_attention(f"Roadblock detected: {gatekeeper.dialog_title}")
        except Exception:
            pass

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
