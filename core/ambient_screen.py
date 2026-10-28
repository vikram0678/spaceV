"""
SpaceV Ambient Screen Observer (Volume I §5.3 & Volume III §24).
Monitors desktop display for:
  - Active window switching (e.g. user moved from VS Code to Browser)
  - Substantial visual content shifts (similarity < 0.85)
  - Pause / resume lifecycle to respect Acoustic Echo Cancellation (AEC) during voice turns.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
import hashlib
import io
import logging
import subprocess
import time
from typing import Any

logger = logging.getLogger("SpaceV.AmbientScreen")


@dataclass
class ScreenChangeEvent:
    """Emitted when significant visual change or active window focus shift occurs."""
    change_type: str          # "app_switch" | "content_change" | "error_dialog"
    similarity_score: float   # 0.0 (totally different) to 1.0 (identical)
    active_window_title: str  # Active window title
    timestamp: float
    screenshot_path: str | None = None

    @property
    def is_significant(self) -> bool:
        return self.similarity_score < 0.85

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_type": self.change_type,
            "similarity_score": self.similarity_score,
            "active_window_title": self.active_window_title,
            "timestamp": self.timestamp,
            "screenshot_path": self.screenshot_path,
            "is_significant": self.is_significant,
        }


class AmbientScreenObserver:
    """
    Background screen observer.
    Downscales screen frames, hashes thumbnail representation, and tracks window title focus.
    """

    IDLE_INTERVAL_SEC: float = 10.0
    ACTIVE_INTERVAL_SEC: float = 30.0
    CHANGE_THRESHOLD: float = 0.85

    def __init__(
        self,
        on_event: Callable[[ScreenChangeEvent], None] | None = None,
        capture_provider: Callable[[], bytes | None] | None = None,
        window_title_provider: Callable[[], str] | None = None,
    ):
        self.on_event = on_event
        self.capture_provider = capture_provider
        self.window_title_provider = window_title_provider or self._get_active_window_title
        self._last_hash: str | None = None
        self._last_title: str = ""
        self._running: bool = False
        self._paused: bool = False
        self._capture_interval: float = self.IDLE_INTERVAL_SEC
        self._observed_events: list[ScreenChangeEvent] = []

    def pause(self):
        """Pauses visual sampling (e.g. during voice output to preserve CPU/audio latency)."""
        self._paused = True

    def resume(self):
        """Resumes visual sampling."""
        self._paused = False

    def set_active_mode(self, active: bool):
        """Adjusts sample cadence: slower when active (30s), faster when idle (10s)."""
        self._capture_interval = self.ACTIVE_INTERVAL_SEC if active else self.IDLE_INTERVAL_SEC

    async def run(self):
        """Main observation loop."""
        self._running = True
        logger.info("[AMBIENT_SCREEN] Screen observer started")

        while self._running:
            if not self._paused:
                try:
                    event = await self.capture_and_compare()
                    if event and self.on_event:
                        self.on_event(event)
                except Exception as e:
                    logger.debug(f"[AMBIENT_SCREEN] Capture error: {e}")

            await asyncio.sleep(self._capture_interval)

    async def capture_and_compare(self) -> ScreenChangeEvent | None:
        """
        Captures current screen state, computes perceptual hash, and evaluates differences.
        """
        # 1. Obtain raw thumbnail bytes
        current_bytes = self._capture_screen_bytes()
        active_title = self.window_title_provider()

        if not current_bytes:
            # Fallback based purely on window title if screen capture is unavailable in headless mode
            if not self._last_title:
                self._last_title = active_title
                return None

            if active_title != self._last_title:
                event = ScreenChangeEvent(
                    change_type="app_switch",
                    similarity_score=0.5,
                    active_window_title=active_title,
                    timestamp=time.time(),
                )
                self._last_title = active_title
                self._observed_events.append(event)
                return event
            return None

        current_hash = hashlib.md5(current_bytes).hexdigest()

        if self._last_hash is None:
            self._last_hash = current_hash
            self._last_title = active_title
            return None

        # Calculate similarity
        similarity = 1.0 if current_hash == self._last_hash else 0.5
        if active_title != self._last_title and self._last_title != "":
            similarity = min(similarity, 0.6)

        event = None
        if similarity < self.CHANGE_THRESHOLD:
            change_type = "app_switch" if active_title != self._last_title else "content_change"
            event = ScreenChangeEvent(
                change_type=change_type,
                similarity_score=similarity,
                active_window_title=active_title,
                timestamp=time.time(),
            )
            self._observed_events.append(event)
            logger.debug(f"[AMBIENT_SCREEN] Event: {change_type} (sim: {similarity:.2f}, title: {active_title})")

        self._last_hash = current_hash
        self._last_title = active_title
        return event

    def _capture_screen_bytes(self) -> bytes | None:
        """Attempts to capture screen bytes via custom provider, mss, or PIL."""
        if self.capture_provider:
            return self.capture_provider()

        try:
            import mss
            from PIL import Image
            with mss.mss() as sct:
                monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                shot = sct.grab(monitor)
                img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
                thumb = img.resize((160, 90))
                buf = io.BytesIO()
                thumb.save(buf, format="JPEG", quality=40)
                return buf.getvalue()
        except Exception:
            return None

    def _get_active_window_title(self) -> str:
        """Inspects active window title using Linux xdotool or returns Unknown."""
        try:
            res = subprocess.run(
                ["xdotool", "getactivewindow", "getwindowname"],
                capture_output=True,
                text=True,
                timeout=1
            )
            if res.returncode == 0:
                title = res.stdout.strip()
                if title:
                    return title
        except Exception:
            pass
        return "Desktop"

    def stop(self):
        self._running = False
        logger.info("[AMBIENT_SCREEN] Screen observer stopped")


# Global singleton instance
ambient_screen_observer = AmbientScreenObserver()
