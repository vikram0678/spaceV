"""
Human-Like Cursor Dynamics & Trajectory Engine for SpaceV.
Implements:
  - Cubic Bézier curves simulating forearm/wrist pivot arcs
  - Minimum-Jerk velocity profiling (Fitts's Law compliant)
  - Micro-tremor, gentle deceleration, and natural button clicks
  - Dual Backend: Native Windows Host Bridge (WSL user32.dll) + PyAutoGUI
  - Visual Reticle & Visor target lock synchronization
"""

from __future__ import annotations

import math
import os
import random
import sys
import time
from typing import Tuple, List

# 1. Bypass optional mouseinfo tkinter dependency on Linux/WSL
if "mouseinfo" not in sys.modules:
    sys.modules["mouseinfo"] = None

try:
    import pyautogui
except Exception:
    pyautogui = None

from core.platform_adapter import PlatformAdapter


def _cubic_bezier(p0: float, p1: float, p2: float, p3: float, t: float) -> float:
    """Calculates coordinate on a 1D cubic Bézier curve at parameter t in [0, 1]."""
    return (1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t**2 * p2 + t**3 * p3


def _minimum_jerk_velocity(t: float) -> float:
    """
    Minimum-jerk polynomial trajectory profile (Fitts's Law).
    Accelerates smoothly from rest, hits peak velocity at t=0.45,
    and gently glides to a stop at t=1.0.
    """
    t = max(0.0, min(1.0, t))
    return 10.0 * (t**3) - 15.0 * (t**4) + 6.0 * (t**5)


def generate_human_path(
    start_x: int, start_y: int, target_x: int, target_y: int, steps: int = 40
) -> List[Tuple[int, int]]:
    """
    Generates realistic, curved human trajectory coordinates between start and target.
    Adds natural perpendicular wrist deflection and micro-jitter.
    """
    dx = target_x - start_x
    dy = target_y - start_y
    distance = math.hypot(dx, dy)

    if distance < 4:
        return [(target_x, target_y)]

    # Dynamic curvature proportional to distance (simulates arm sweep)
    deviation = min(distance * 0.20, 100.0)
    perp_x = -dy / distance
    perp_y = dx / distance

    # Randomize whether arm swings inward or outward
    swing_dir = random.choice([-1, 1])

    # Control Point 1 (around 30% of travel)
    p1_x = start_x + (dx * 0.30) + (perp_x * deviation * 0.8 * swing_dir)
    p1_y = start_y + (dy * 0.30) + (perp_y * deviation * 0.8 * swing_dir)

    # Control Point 2 (around 70% of travel)
    p2_x = start_x + (dx * 0.70) + (perp_x * deviation * 0.3 * swing_dir)
    p2_y = start_y + (dy * 0.70) + (perp_y * deviation * 0.3 * swing_dir)

    points = []
    for step in range(steps):
        raw_t = step / float(steps - 1)
        t = _minimum_jerk_velocity(raw_t)

        x = _cubic_bezier(start_x, p1_x, p2_x, target_x, t)
        y = _cubic_bezier(start_y, p1_y, p2_y, target_y, t)

        # Micro-tremor (0.5 to 1.5px organic hand vibration)
        if 0.15 < raw_t < 0.88:
            x += random.uniform(-1.0, 1.0)
            y += random.uniform(-1.0, 1.0)

        points.append((int(round(x)), int(round(y))))

    return points


def human_move_to(target_x: int, target_y: int, speed: str = "normal") -> str:
    """
    Glides cursor to (target_x, target_y) using human Bézier trajectories, minimum-jerk physics,
    and biological target overshoot correction (evading anti-bot telemetry).
    Works seamlessly across native Windows, WSL, and Linux.
    """
    from tools.gui_tools import safety
    safety.check()
    # 1. Get current mouse position
    start_x, start_y = 960, 540
    if pyautogui:
        try:
            pos = pyautogui.position()
            start_x, start_y = pos.x, pos.y
        except Exception:
            pass

    distance = math.hypot(target_x - start_x, target_y - start_y)
    if distance < 3:
        return f"Cursor already at ({target_x}, {target_y})"

    duration_map = {
        "fast": max(0.18, min(0.38, distance / 2400.0)),
        "normal": max(0.35, min(0.65, distance / 1500.0)),
        "careful": max(0.60, min(1.10, distance / 900.0)),
    }
    total_duration = duration_map.get(speed, 0.50)

    # Biological overshoot simulation for distances > 140px (natural human motor control signature)
    has_overshoot = distance > 140 and random.random() < 0.40
    intermediate_target_x = target_x + int(random.uniform(-4, 4)) if has_overshoot else target_x
    intermediate_target_y = target_y + int(random.uniform(-4, 4)) if has_overshoot else target_y

    steps = max(20, int(total_duration * 50))
    path = generate_human_path(start_x, start_y, intermediate_target_x, intermediate_target_y, steps=steps)
    if has_overshoot:
        # Micro-correction settling step onto exact center
        path.append((target_x, target_y))

    # 2. Check if running in WSL -> Dispatch via HostBridge user32.dll SetCursorPos
    if PlatformAdapter.is_wsl():
        from core.host_bridge import HostBridge

        # Subsample path to 12 smooth keyframes for fast IPC dispatch
        step_stride = max(1, len(path) // 12)
        sampled = path[::step_stride]
        if path[-1] not in sampled:
            sampled.append(path[-1])

        pts_loop = "; ".join([f"[HostInput]::SetCursorPos({x},{y}); Start-Sleep -Milliseconds 18" for x, y in sampled])
        ps_cmd = (
            "Add-Type -TypeDefinition '"
            "using System; using System.Runtime.InteropServices; "
            "public class HostInput { "
            '[DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y); '
            "}'; "
            f"{pts_loop}"
        )
        HostBridge.execute_powershell(ps_cmd)
        return f"Human-glided cursor to ({target_x}, {target_y}) in {total_duration:.2f}s (WSL HostBridge)"

    # 3. Native PyAutoGUI path
    if pyautogui:
        interval = total_duration / float(len(path))
        for px, py in path:
            try:
                pyautogui.moveTo(px, py)
                time.sleep(interval)
            except Exception:
                pass

    return f"Moved smoothly to ({target_x}, {target_y}) in {total_duration:.2f}s"


def human_click(target_x: int = None, target_y: int = None, button: str = "left") -> str:
    """Moves human-like to coordinates (if given) and clicks with natural press-release delay."""
    from tools.gui_tools import safety
    safety.check()
    if target_x is not None and target_y is not None:
        human_move_to(target_x, target_y, speed="normal")

    if PlatformAdapter.is_wsl():
        from core.host_bridge import HostBridge

        HostBridge.click_host_coordinate(target_x or 960, target_y or 540, clicks=1, button=button)
        return f"Human-clicked {button} at ({target_x}, {target_y}) via WSL HostBridge"

    if pyautogui:
        pyautogui.mouseDown(button=button)
        time.sleep(random.uniform(0.065, 0.115))
        pyautogui.mouseUp(button=button)

    return f"Human-clicked {button} at cursor position"
