"""
High-Performance Multi-Tier Desktop Vision Capture Engine for SpaceV.
Powered by DirectX 11 / DXGI Desktop Duplication (via bettercam) for ultra-low latency (<1.5ms)
direct GPU VRAM capture, with automatic fallback to Windows GDI Host capture.
"""
from __future__ import annotations

import logging

import numpy as np
from PIL import Image

logger = logging.getLogger("SpaceV.ScreenCapture")

_BETTERCAM_INSTANCE = None
_BETTERCAM_FAILED = False
_ACTIVE_TIER = "Unknown"


def _init_bettercam():
    """Lazily and safely attempts to initialize BetterCam DXGI output."""
    global _BETTERCAM_INSTANCE, _BETTERCAM_FAILED, _ACTIVE_TIER
    if _BETTERCAM_FAILED:
        return None
    if _BETTERCAM_INSTANCE is not None:
        return _BETTERCAM_INSTANCE

    try:
        import bettercam

        # Safe monkeypatch to prevent AttributeError if __init__ fails early
        def _safe_del(self):
            try:
                if hasattr(self, "is_capturing"):
                    self.release()
            except Exception:
                pass
        bettercam.BetterCam.__del__ = _safe_del

        _BETTERCAM_INSTANCE = bettercam.create(output_color="RGB")
        _ACTIVE_TIER = "DXGI (DirectX 11 GPU VRAM)"
        logger.info("[ScreenCapture] ⚡ BetterCam DXGI Desktop Duplication initialized successfully.")
        return _BETTERCAM_INSTANCE
    except Exception as e:
        logger.debug(f"[ScreenCapture] DXGI initialization bypassed ({e}); falling back to GDI Host capture.")
        _BETTERCAM_FAILED = True
        _BETTERCAM_INSTANCE = None
        _ACTIVE_TIER = "GDI (Windows Desktop Host)"
        return None


def capture_desktop_cv2() -> np.ndarray | None:
    """
    Captures the interactive desktop display as a NumPy RGB array.
    Uses DXGI direct VRAM duplication if available, with transparent GDI fallback.
    """
    global _ACTIVE_TIER
    cam = _init_bettercam()
    if cam is not None:
        try:
            frame = cam.grab()
            if frame is not None and frame.size > 0:
                _ACTIVE_TIER = "DXGI (DirectX 11 GPU VRAM)"
                return frame
        except Exception:
            pass

    # Tier 2 Fallback: GDI Host Capture
    pil_img = _gdi_capture_fallback()
    if pil_img is not None:
        _ACTIVE_TIER = "GDI (Windows Desktop Host)"
        return np.array(pil_img)

    return None


def capture_desktop_pil() -> Image.Image | None:
    """
    Captures the interactive desktop display as a PIL Image.
    Uses DXGI direct VRAM duplication (<1.5ms) if available, with transparent GDI fallback.
    """
    global _ACTIVE_TIER
    cam = _init_bettercam()
    if cam is not None:
        try:
            frame = cam.grab()
            if frame is not None and frame.size > 0:
                _ACTIVE_TIER = "DXGI (DirectX 11 GPU VRAM)"
                return Image.fromarray(frame)
        except Exception:
            pass

    # Tier 2 Fallback: GDI Host Capture
    img = _gdi_capture_fallback()
    if img is not None:
        _ACTIVE_TIER = "GDI (Windows Desktop Host)"
    return img


def _gdi_capture_fallback() -> Image.Image | None:
    """Fallback capture using PIL ImageGrab or PyAutoGUI GDI screenshot."""
    try:
        from PIL import ImageGrab
        return ImageGrab.grab()
    except Exception:
        try:
            import pyautogui
            return pyautogui.screenshot()
        except Exception:
            return None


def get_active_capture_tier() -> str:
    """Returns the currently active capture engine tier."""
    global _ACTIVE_TIER
    if _ACTIVE_TIER == "Unknown":
        # Probe once
        capture_desktop_pil()
    return _ACTIVE_TIER
