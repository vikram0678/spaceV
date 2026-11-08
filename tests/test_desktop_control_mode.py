"""Safety and state tests for the explicit desktop input mode."""

import pytest

from tools.gui_tools import CURSOR_SPEED_PRESETS, safety


def test_desktop_input_is_blocked_when_mode_is_off(monkeypatch):
    from tools import human_motion

    previous_mode = safety.autonomous_mode_enabled
    safety.set_desktop_control(False)
    moved = []
    monkeypatch.setattr(human_motion.pyautogui, "moveTo", lambda *args, **kwargs: moved.append(args))
    try:
        with pytest.raises(PermissionError, match="Desktop control is off"):
            human_motion.human_move_to(500, 500)
        assert moved == []
    finally:
        safety.set_desktop_control(previous_mode)


def test_host_keyboard_and_mouse_bridge_are_blocked_when_mode_is_off(monkeypatch):
    from core.host_bridge import HostBridge

    previous_mode = safety.autonomous_mode_enabled
    safety.set_desktop_control(False)
    called = []
    monkeypatch.setattr(HostBridge, "execute_powershell", lambda *args, **kwargs: called.append(args))
    try:
        with pytest.raises(PermissionError, match="Desktop control is off"):
            HostBridge.click_host_coordinate(100, 100)
        with pytest.raises(PermissionError, match="Desktop control is off"):
            HostBridge.press_host_hotkey(["ctrl", "l"])
        assert called == []
    finally:
        safety.set_desktop_control(previous_mode)


def test_speed_options_are_exact_and_monotonic():
    assert list(CURSOR_SPEED_PRESETS) == ["0.1x", "0.3x", "0.5x", "0.8x", "1.0x"]
    assert [CURSOR_SPEED_PRESETS[key]["multiplier"] for key in CURSOR_SPEED_PRESETS] == [0.1, 0.3, 0.5, 0.8, 1.0]
