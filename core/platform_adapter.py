"""
Universal Cross-Platform Operating System Adapter for SpaceV.
Ensures seamless desktop application launch, URL opening, and process control
across Windows, WSL (bridging to host Windows desktop), macOS, and native Linux.
"""
import logging
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("SpaceV.PlatformAdapter")

# Common application binary aliases
LINUX_APP_MAP = {
    "chrome": ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"],
    "browser": ["google-chrome", "google-chrome-stable", "chromium", "firefox", "x-www-browser"],
    "calculator": ["gnome-calculator", "kcalc", "xcalc"],
    "calc": ["gnome-calculator", "kcalc", "xcalc"],
    "notepad": ["gedit", "kate", "mousepad", "nano", "xed"],
    "paint": ["gimp", "kolourpaint", "drawing", "pinta"],
    "mspaint": ["gimp", "kolourpaint", "drawing", "pinta"],
    "terminal": ["gnome-terminal", "konsole", "xfce4-terminal", "xterm"],
    "code": ["code"],
    "vscode": ["code"],
    "task manager": ["gnome-system-monitor", "ksysguard", "htop"],
    "taskmgr": ["gnome-system-monitor", "ksysguard", "htop"],
}

WINDOWS_APP_MAP = {
    "calculator": "calc",
    "calc": "calc",
    "notepad": "notepad",
    "chrome": "chrome",
    "browser": "chrome",
    "google chrome": "chrome",
    "paint": "mspaint",
    "mspaint": "mspaint",
    "task manager": "taskmgr",
    "taskmgr": "taskmgr",
    "terminal": "wt",
    "code": "code",
    "vscode": "code",
    "settings": "ms-settings:",
    "explorer": "explorer",
}


class PlatformAdapter:
    """
    Production-grade platform bridge for SpaceV.
    Dynamically routes OS operations to the optimal native or bridged subsystem.
    """
    _is_wsl_cached: bool | None = None

    @classmethod
    def is_wsl(cls) -> bool:
        """Determines if running inside WSL (Windows Subsystem for Linux)."""
        if cls._is_wsl_cached is None:
            cls._is_wsl_cached = False
            if sys.platform.startswith("linux"):
                try:
                    version_path = Path("/proc/version")
                    if version_path.exists():
                        content = version_path.read_text().lower()
                        if "microsoft" in content or "wsl" in content:
                            cls._is_wsl_cached = True
                except Exception:
                    pass
        return cls._is_wsl_cached

    @classmethod
    def launch_app(cls, app_name: str) -> str:
        """
        Launches an application cross-platform without platform command failures.
        """
        clean = app_name.strip().lower()

        # 1. WSL: Bridge to Host Windows Desktop
        if cls.is_wsl():
            win_target = WINDOWS_APP_MAP.get(clean, clean)
            try:
                # cmd.exe /c start "" <target> handles Windows GUI launching from WSL
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", win_target],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return f"Launched Windows application: '{clean}'"
            except Exception as e:
                logger.warning(f"[PlatformAdapter] WSL cmd.exe bridge failed: {e}")

        # 2. Native Windows
        if sys.platform == "win32":
            win_target = WINDOWS_APP_MAP.get(clean, clean)
            try:
                subprocess.Popen(f"start \"\" \"{win_target}\"", shell=True)
                return f"Launched Windows application: '{clean}'"
            except Exception as e:
                return f"Failed to launch '{clean}': {e}"

        # 3. macOS
        if sys.platform == "darwin":
            try:
                subprocess.Popen(["open", "-a", clean])
                return f"Launched macOS application: '{clean}'"
            except Exception as e:
                return f"Failed to launch '{clean}': {e}"

        # 4. Native Linux (Ubuntu, Debian, Fedora, Arch)
        linux_binaries = LINUX_APP_MAP.get(clean, [clean])
        for bin_name in linux_binaries:
            found = shutil.which(bin_name)
            if found:
                try:
                    subprocess.Popen([found], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    return f"Launched Linux application: '{bin_name}'"
                except Exception as e:
                    return f"Failed to start '{bin_name}': {e}"

        # Fallback to xdg-open if present
        if shutil.which("xdg-open"):
            try:
                subprocess.Popen(["xdg-open", clean], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return f"Attempted to launch via xdg-open: '{clean}'"
            except Exception as e:
                return f"Failed to launch via xdg-open: {e}"

        return f"Application '{app_name}' is not recognized in this environment."

    @classmethod
    def open_url(cls, url: str) -> str:
        """
        Opens a URL in the user's default browser across Windows, WSL, macOS, and Linux.
        """
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "https://" + url

        # 1. WSL: Bridge to Host Windows Browser
        if cls.is_wsl():
            try:
                subprocess.Popen(
                    ["cmd.exe", "/c", "start", "", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return f"Opened website in Windows browser: {url}"
            except Exception as e:
                logger.warning(f"[PlatformAdapter] WSL URL bridge failed: {e}")

        # 2. Native webbrowser module (works on native Windows, macOS, native Linux)
        import webbrowser
        try:
            webbrowser.open(url)
            return f"Opened website: {url}"
        except Exception as e:
            return f"Failed to open URL '{url}': {e}"


platform_adapter = PlatformAdapter()
