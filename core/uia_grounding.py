"""
Windows UI Automation (UIA) Native Fast-Path Grounding Engine for SpaceV.
Queries Windows UIAutomationCore.dll directly via COM to discover native buttons,
inputs, tabs, and menus in <1ms without taking a screenshot, with automatic
fallback to Windows Native OCR visual grounding.
"""
from __future__ import annotations

import logging
import time
from typing import Any

try:
    import comtypes.client
    HAS_COMTYPES = True
except ImportError:
    HAS_COMTYPES = False

import pyautogui

from tools.gui_tools import human_move_to, safety

logger = logging.getLogger("SpaceV.UIA")

_UIA_ENGINE = None
_UIA_INITIALIZED = False


def _get_uia_client():
    """Lazily initializes and caches the Windows UIAutomation COM client."""
    global _UIA_ENGINE, _UIA_INITIALIZED
    if _UIA_INITIALIZED:
        return _UIA_ENGINE

    if not HAS_COMTYPES:
        _UIA_INITIALIZED = True
        return None

    try:
        mod = comtypes.client.GetModule("UIAutomationCore.dll")
        _UIA_ENGINE = comtypes.client.CreateObject(mod.CUIAutomation)
        _UIA_INITIALIZED = True
        logger.info("[UIA] ⚡ Windows UIAutomationCore client initialized successfully.")
    except Exception as e:
        logger.warning(f"[UIA] Failed to initialize UIAutomationCore: {e}")
        _UIA_ENGINE = None
        _UIA_INITIALIZED = True

    return _UIA_ENGINE


def find_control_by_name(
    target_name: str,
    hwnd: int | None = None,
    max_depth: int = 4
) -> tuple[int, int, str, str] | None:
    """
    Searches the Windows UI Automation tree for a control matching target_name.
    Returns:
        (center_x, center_y, matched_name, control_type) or None if not found.
    """
    uia = _get_uia_client()
    if uia is None:
        return None

    clean_target = target_name.lower().strip()
    try:
        if hwnd:
            root = uia.ElementFromHandle(hwnd)
        else:
            root = uia.GetRootElement()

        if root is None:
            return None

        # Build search condition for control type or walk tree
        # Walk active window's children for fast discovery
        queue = [(root, 0)]
        while queue:
            elem, depth = queue.pop(0)
            if depth > max_depth:
                continue

            try:
                name = elem.CurrentName or ""
                clean_name = name.lower().strip()
                if clean_name and (clean_target in clean_name or clean_name in clean_target):
                    rect = elem.CurrentBoundingRectangle
                    # Validate non-zero geometry
                    width = rect.right - rect.left
                    height = rect.bottom - rect.top
                    if width > 4 and height > 4:
                        cx = int(rect.left + width // 2)
                        cy = int(rect.top + height // 2)
                        ctrl_type = str(elem.CurrentLocalizedControlType or "Control")
                        return (cx, cy, name, ctrl_type)

                # Traverse children
                if depth < max_depth:
                    walker = uia.ControlViewWalker
                    child = walker.GetFirstChildElement(elem)
                    child_count = 0
                    while child and child_count < 30:
                        queue.append((child, depth + 1))
                        child = walker.GetNextSiblingElement(child)
                        child_count += 1
            except Exception:
                continue

    except Exception as e:
        logger.debug(f"[UIA] Traversal error: {e}")

    return None


def list_interactive_controls(hwnd: int | None = None, limit: int = 15) -> list[dict[str, Any]]:
    """
    Lists interactive buttons, menus, and controls in the active or specified window.
    """
    uia = _get_uia_client()
    if uia is None:
        return []

    controls = []
    try:
        root = uia.ElementFromHandle(hwnd) if hwnd else uia.GetRootElement()
        if not root:
            return []

        walker = uia.ControlViewWalker
        child = walker.GetFirstChildElement(root)
        while child and len(controls) < limit:
            try:
                name = child.CurrentName
                ctrl_type = child.CurrentLocalizedControlType
                rect = child.CurrentBoundingRectangle
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if name and w > 4 and h > 4:
                    controls.append({
                        "name": name,
                        "type": str(ctrl_type),
                        "x": int(rect.left + w // 2),
                        "y": int(rect.top + h // 2),
                    })
            except Exception:
                pass
            child = walker.GetNextSiblingElement(child)
    except Exception as e:
        logger.debug(f"[UIA] List controls error: {e}")

    return controls


def gui_click_control(target_name: str) -> str:
    """
    Dual-Tier Grounding:
    1. First attempts <1ms Windows Native UIAutomation tree resolution.
    2. If not found in UIA tree, falls back to Windows Native OCR visual grounding.
    Glides cursor to exact center and clicks.
    """
    safety.reset()
    try:
        # Tier 1: UIA Native Control Fast-Path
        uia_match = find_control_by_name(target_name)
        if uia_match:
            cx, cy, matched_name, ctrl_type = uia_match
            print(f"  [UIA FAST-PATH] ⚡ Found native {ctrl_type} '{matched_name}' at ({cx}, {cy})")
            human_move_to(cx, cy, duration=0.4, label=f"⚡ CLICKING {ctrl_type.upper()} '{matched_name}'", mode="clicking")
            safety.check()
            time.sleep(0.08)
            pyautogui.click()
            try:
                from ui.cursor_overlay import hide_cursor_hud
                hide_cursor_hud()
            except Exception:
                pass
            return f"Autonomously located native {ctrl_type} '{matched_name}' via UIA fast-path at ({cx}, {cy}) and clicked successfully!"

        # Tier 2: OCR Visual Fallback
        print(f"  [UIA FAST-PATH] Control '{target_name}' not in accessibility tree. Falling back to Native OCR...")
        from core.vision_grounding import gui_click_text
        return gui_click_text(target_name)

    except pyautogui.FailSafeException:
        safety.abort()
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered."
    except InterruptedError as e:
        return f"⚠️ EMERGENCY STOP: {e!s}"
    except Exception as e:
        return f"Control click failed: {e!s}"
