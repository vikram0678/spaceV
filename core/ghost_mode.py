"""
Ghost Mode (Dual-Plane Multi-Desktop & Background Automation Subsystem) for SpaceV.
Allows SpaceV to run headless browser operations, downloads, and system tasks
in isolated background sessions without stealing the user's physical mouse and keyboard.
"""
from __future__ import annotations

import logging
import os
import subprocess

from core.memory import memory

logger = logging.getLogger("SpaceV.GhostMode")


class GhostModeManager:
    """
    Coordinates foreground cybernetic cursor vs isolated background 'Ghost Plane' automation.
    """

    PREF_KEY = "ghost_mode_enabled"

    def __init__(self):
        self._is_active = bool(memory.get(self.PREF_KEY, False))

    @property
    def is_active(self) -> bool:
        """Returns True if Ghost Mode background automation is active."""
        return self._is_active

    def enable(self) -> str:
        """Activates Ghost Mode background execution."""
        self._is_active = True
        memory.set(self.PREF_KEY, True)
        logger.info("[GHOST MODE] 👻 Ghost Plane automation activated. Physical cursor will not be hijacked.")
        return "Ghost Mode is now ACTIVE, Sir. Background tasks will execute silently without interrupting your mouse or keyboard."

    def disable(self) -> str:
        """Restores standard Foreground HUD mode."""
        self._is_active = False
        memory.set(self.PREF_KEY, False)
        logger.info("[GHOST MODE] 🖥️ Foreground automation restored with Cybernetic Cursor HUD.")
        return "Ghost Mode DEACTIVATED, Sir. Full cybernetic visual cursor HUD is now restored."

    def get_status(self) -> str:
        """Returns active automation plane status."""
        if self._is_active:
            return "Ghost Mode is currently ACTIVE (Isolated background execution enabled)."
        return "Ghost Mode is currently INACTIVE (Foreground cybernetic cursor HUD active)."

    def execute_silent_process(
        self,
        command: list[str] | str,
        cwd: str | None = None,
        timeout_sec: int = 60
    ) -> tuple[int, str]:
        """
        Executes a background OS command or automation script with hidden window flags.
        Never flashes a console window or steals OS window focus.
        """
        try:
            # Windows-specific hidden process flags
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NO_WINDOW | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

            shell = isinstance(command, str)
            proc = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                stdin=subprocess.PIPE,
                text=True,
                cwd=cwd,
                shell=shell,
                creationflags=creationflags
            )
            stdout, stderr = proc.communicate(timeout=timeout_sec)
            output = (stdout or "") + ("\n" + stderr if stderr else "")
            return proc.returncode, output.strip()
        except subprocess.TimeoutExpired:
            proc.kill()
            return -1, "Background execution timed out."
        except Exception as e:
            return -1, f"Failed to spawn ghost process: {e!s}"


ghost_manager = GhostModeManager()
