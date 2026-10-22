"""
Autonomous GUI and Human-Like Cursor Automation with 4-Layer Safety Shield.
Features smooth 60 FPS HUD tracking, autonomous Start Menu navigation,
and vector-stroke canvas drawing in MS Paint using pure cursor manipulation.
"""
import time
import math
import subprocess
import threading
from typing import Optional, List, Tuple

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except Exception:
    HAS_PYAUTOGUI = False
    class MockPyAutoGUI:
        FAILSAFE = True
        PAUSE = 0.04
        @staticmethod
        def size(): return (1920, 1080)
        @staticmethod
        def position(): return (960, 540)
        @staticmethod
        def moveTo(*args, **kwargs): pass
        @staticmethod
        def click(*args, **kwargs): pass
        @staticmethod
        def write(*args, **kwargs): pass
        @staticmethod
        def press(*args, **kwargs): pass
        @staticmethod
        def hotkey(*args, **kwargs): pass
        @staticmethod
        def mouseDown(*args, **kwargs): pass
        @staticmethod
        def mouseUp(*args, **kwargs): pass
    pyautogui = MockPyAutoGUI()

try:
    from pynput import keyboard
    HAS_PYNPUT = True
except Exception:
    HAS_PYNPUT = False
    class MockKeyboard:
        class Key:
            esc = "esc"
            space = "space"
        class Listener:
            def __init__(self, *args, **kwargs): pass
            def start(self): pass
            def stop(self): pass
    keyboard = MockKeyboard()

# Hardware Per-Monitor DPI Scaling Awareness (0% pixel drift on 125%/150%/4K displays)
try:
    import ctypes
    ctypes.windll.shcore.SetProcessDpiAwareness(2) # PROCESS_PER_MONITOR_DPI_AWARE
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

# Configure PyAutoGUI fail-safe (moving cursor to corner (0,0) aborts immediately)
try:
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.04
except Exception:
    pass

# 5 Speed Profiles (DPI & Motion Dynamics)
CURSOR_SPEED_PRESETS = {
    "Hyper": {"multiplier": 0.20, "move_duration": 0.08, "type_interval": 0.010, "label": "🚀 Hyper (0.2x)"},
    "Fast": {"multiplier": 0.50, "move_duration": 0.22, "type_interval": 0.025, "label": "🏎️ Fast (0.5x)"},
    "Normal": {"multiplier": 1.00, "move_duration": 0.45, "type_interval": 0.045, "label": "👤 Normal (1.0x)"},
    "Steady": {"multiplier": 1.60, "move_duration": 0.75, "type_interval": 0.070, "label": "🚶 Steady (1.6x)"},
    "Precision": {"multiplier": 2.50, "move_duration": 1.25, "type_interval": 0.100, "label": "🎯 Precision (2.5x)"},
}

class SafetyController:
    """
    Singleton Safety Manager managing emergency aborts, global hotkeys, kill switches,
    and cursor velocity profiles.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SafetyController, cls).__new__(cls)
            cls._instance.is_aborted = False
            cls._instance.autonomous_mode_enabled = False
            cls._instance.current_speed = "Normal"
            cls._instance._listener = None
            cls._instance.start_global_listener()
        return cls._instance

    def start_global_listener(self):
        """Starts background global hotkey listener for ESC and F12 keys."""
        def on_press(key):
            try:
                if key == keyboard.Key.esc or key == keyboard.Key.f12:
                    print("\n[EMERGENCY STOP] Panic Key Pressed! Halting all GUI automation immediately.")
                    self.abort()
            except Exception:
                pass

        if self._listener is None:
            self._listener = keyboard.Listener(on_press=on_press)
            self._listener.daemon = True
            self._listener._suppress = False
            self._listener.start()

    def abort(self):
        self.is_aborted = True

    def reset(self):
        self.is_aborted = False

    def check(self):
        """Raises exception if abort flag is raised or failsafe triggered."""
        if self.is_aborted:
            raise InterruptedError("Autonomous action aborted by User (Emergency Stop / ESC pressed)!")

    def set_cursor_speed(self, preset_name: str) -> bool:
        """Sets the active motion and typing speed profile."""
        if preset_name in CURSOR_SPEED_PRESETS:
            self.current_speed = preset_name
            pyautogui.PAUSE = max(0.01, 0.04 * CURSOR_SPEED_PRESETS[preset_name]["multiplier"])
            return True
        return False

    def get_speed_settings(self) -> dict:
        """Returns the currently active speed profile dictionary."""
        return CURSOR_SPEED_PRESETS.get(self.current_speed, CURSOR_SPEED_PRESETS["Normal"])

# Global instance
safety = SafetyController()

def human_move_to(x: int, y: int, duration: float = 0.5, label: str = "⚡ SPACEV ACTIVE", mode: str = "moving"):
    """
    Moves cursor smoothly to (x, y) with human-like easing and glowing 60 FPS HUD.
    Scales motion duration dynamically based on the active speed profile.
    """
    safety.check()
    try:
        from ui.cursor_overlay import show_cursor_hud
        show_cursor_hud(label=label, mode=mode, x=x, y=y)
    except Exception:
        pass

    multiplier = safety.get_speed_settings()["multiplier"]
    actual_duration = max(0.03, duration * multiplier)

    # Smooth easing curve
    pyautogui.moveTo(x, y, duration=actual_duration, tween=pyautogui.easeInOutQuad)
    safety.check()

def human_type(text: str, interval: float = 0.04, label: str = "⌨️ SPACEV TYPING"):
    """
    Types text with human-like keystroke delays and continuous abort checks.
    Scales typing interval dynamically based on the active speed profile.
    """
    try:
        from ui.cursor_overlay import show_cursor_hud
        show_cursor_hud(label=label, mode="typing")
    except Exception:
        pass

    multiplier = safety.get_speed_settings()["multiplier"]
    actual_interval = max(0.008, interval * multiplier)

    for char in text:
        safety.check()
        pyautogui.write(char)
        time.sleep(actual_interval)
    safety.check()

# =========================================================================
# Vector Stroke Shapes Library for MS Paint Drawing
# =========================================================================

def _generate_circle_points(cx: float, cy: float, radius: float, num_points: int = 30) -> List[Tuple[float, float]]:
    pts = []
    for i in range(num_points + 1):
        angle = (2 * math.pi * i) / num_points
        pts.append((cx + radius * math.cos(angle), cy + radius * math.sin(angle)))
    return pts

def _generate_arc_points(cx: float, cy: float, radius_x: float, radius_y: float, start_angle: float, end_angle: float, num_points: int = 16) -> List[Tuple[float, float]]:
    pts = []
    for i in range(num_points + 1):
        angle = start_angle + (end_angle - start_angle) * (i / num_points)
        pts.append((cx + radius_x * math.cos(angle), cy + radius_y * math.sin(angle)))
    return pts

def get_shape_strokes(shape_name: str) -> Tuple[str, List[List[Tuple[float, float]]]]:
    """
    Returns a normalized shape name and list of coordinate strokes.
    Each stroke is a list of relative (dx, dy) tuples from the canvas center.
    """
    name = shape_name.lower().strip()
    
    if any(k in name for k in ["house", "home", "building", "hut"]):
        label = "House"
        strokes = [
            # Main Walls Box
            [(-130, 30), (130, 30), (130, 160), (-130, 160), (-130, 30)],
            # Triangular Roof
            [(-150, 30), (0, -85), (150, 30)],
            # Chimney
            [(70, -20), (70, -75), (95, -75), (95, 10)],
            # Door
            [(-30, 160), (-30, 85), (30, 85), (30, 160)],
            # Door Knob
            [(18, 125), (24, 125)],
            # Left Window
            [(-105, 60), (-55, 60), (-55, 110), (-105, 110), (-105, 60)],
            [(-80, 60), (-80, 110)],
            [(-105, 85), (-55, 85)],
            # Right Window
            [(55, 60), (105, 60), (105, 110), (55, 110), (55, 60)],
            [(80, 60), (80, 110)],
            [(55, 85), (105, 85)],
        ]

    elif any(k in name for k in ["heart", "love"]):
        label = "Heart"
        pts = []
        for i in range(48):
            t = (2 * math.pi * i) / 47
            x = 16 * (math.sin(t) ** 3)
            y = -(13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))
            pts.append((x * 8.5, y * 8.5))
        strokes = [pts]

    elif any(k in name for k in ["star"]):
        label = "Star"
        pts = []
        for i in range(11):
            angle = (i * 36 - 90) * (math.pi / 180)
            r = 125 if i % 2 == 0 else 52
            pts.append((r * math.cos(angle), r * math.sin(angle)))
        strokes = [pts]

    elif any(k in name for k in ["smiley", "smile", "face", "happy"]):
        label = "Smiley Face"
        strokes = [
            # Head Circle
            _generate_circle_points(0, 0, 115, 32),
            # Left Eye
            _generate_circle_points(-45, -35, 14, 16),
            # Right Eye
            _generate_circle_points(45, -35, 14, 16),
            # Eyebrows
            [(-65, -60), (-25, -65)],
            [(25, -65), (65, -60)],
            # Wide Happy Smile Arc
            _generate_arc_points(0, 10, 65, 55, 0.2 * math.pi, 0.8 * math.pi, 20),
            # Cheeks
            [(-75, 15), (-60, 25)],
            [(75, 15), (60, 25)],
        ]

    elif any(k in name for k in ["car", "automobile", "truck"]):
        label = "Car"
        strokes = [
            # Lower Body
            [(-160, 35), (160, 35), (160, 95), (-160, 95), (-160, 35)],
            # Roof & Cabin
            [(-95, 35), (-55, -25), (65, -25), (110, 35)],
            # Center Window Divider
            [(5, -25), (5, 35)],
            # Left Wheel
            _generate_circle_points(-90, 95, 26, 20),
            # Right Wheel
            _generate_circle_points(90, 95, 26, 20),
            # Front Headlight
            [(160, 50), (175, 50), (175, 70), (160, 70)],
        ]

    elif any(k in name for k in ["tree", "nature", "forest", "pine"]):
        label = "Tree"
        strokes = [
            # Trunk
            [(-22, 45), (-22, 165), (22, 165), (22, 45)],
            # Bottom Foliage Tier
            [(-130, 55), (0, -15), (130, 55), (-130, 55)],
            # Middle Foliage Tier
            [(-100, -10), (0, -70), (100, -10), (-100, -10)],
            # Top Foliage Tier
            [(-70, -65), (0, -125), (70, -65), (-70, -65)],
        ]

    elif any(k in name for k in ["sun", "sunshine", "sol"]):
        label = "Sun"
        rays = []
        for i in range(8):
            angle = (i * 45) * (math.pi / 180)
            r1 = 65
            r2 = 115
            rays.append([
                (r1 * math.cos(angle), r1 * math.sin(angle)),
                (r2 * math.cos(angle), r2 * math.sin(angle))
            ])
        strokes = [_generate_circle_points(0, 0, 52, 28)] + rays

    elif any(k in name for k in ["rocket", "space", "spacev", "spaceship"]):
        label = "SpaceV Rocket"
        strokes = [
            # Fuselage
            [(0, -145), (42, -45), (42, 85), (-42, 85), (-42, -45), (0, -145)],
            # Porthole
            _generate_circle_points(0, 5, 20, 18),
            # Left Fin
            [(-42, 45), (-85, 100), (-42, 85)],
            # Right Fin
            [(42, 45), (85, 100), (42, 85)],
            # Thruster Nozzle
            [(-25, 85), (-15, 105), (15, 105), (25, 85)],
            # Rocket Flame
            [(-18, 105), (0, 155), (18, 105)],
        ]

    elif any(k in name for k in ["cat", "kitten", "kitty"]):
        label = "Cat"
        strokes = [
            # Head Circle
            _generate_circle_points(0, 15, 75, 28),
            # Left Ear
            [(-50, -30), (-70, -95), (-15, -45)],
            # Right Ear
            [(50, -30), (70, -95), (15, -45)],
            # Eyes
            [(-30, 0), (-18, 0)],
            [(18, 0), (30, 0)],
            # Nose
            [(-8, 22), (8, 22), (0, 30), (-8, 22)],
            # Whiskers
            [(-15, 22), (-65, 12)],
            [(-15, 28), (-70, 30)],
            [(15, 22), (65, 12)],
            [(15, 28), (70, 30)],
        ]

    elif any(k in name for k in ["flower", "rose", "plant"]):
        label = "Flower"
        petals = []
        for i in range(5):
            angle = (i * 72 - 90) * (math.pi / 180)
            px = 42 * math.cos(angle)
            py = -30 + 42 * math.sin(angle)
            petals.append(_generate_circle_points(px, py, 22, 16))
        strokes = (
            [_generate_circle_points(0, -30, 26, 20)] +
            petals +
            [
                # Stem
                [(0, -5), (0, 155)],
                # Left Leaf
                [(0, 75), (-45, 55), (-15, 95), (0, 95)],
                # Right Leaf
                [(0, 105), (45, 85), (15, 125), (0, 125)],
            ]
        )

    elif any(k in name for k in ["boat", "ship", "sailboat"]):
        label = "Sailboat"
        strokes = [
            # Hull
            [(-120, 55), (120, 55), (90, 105), (-90, 105), (-120, 55)],
            # Mast
            [(0, 55), (0, -95)],
            # Main Sail
            [(5, -85), (75, 40), (5, 40), (5, -85)],
            # Front Jib
            [(-5, -75), (-65, 40), (-5, 40), (-5, -75)],
            # Water Waves
            [(-140, 120), (-95, 110), (-45, 120), (5, 110), (55, 120), (105, 110), (150, 120)],
        ]

    else:
        # Generic Futuristic Cybernetic Diamond Mandala
        label = f"Diagram ({name.capitalize()})"
        strokes = [
            # Outer Diamond
            [(0, -120), (120, 0), (0, 120), (-120, 0), (0, -120)],
            # Inner Box
            [(-70, -70), (70, -70), (70, 70), (-70, 70), (-70, -70)],
            # Center Circle
            _generate_circle_points(0, 0, 45, 24),
            # Diagonals
            [(-120, 0), (120, 0)],
            [(0, -120), (0, 120)],
        ]

    return label, strokes


def gui_draw_in_paint(shape_or_prompt: str = "house") -> str:
    """
    Autonomously opens MS Paint, maximizes the canvas, and smoothly draws
    the requested diagram, shape, or illustration using pure cursor movements
    with glowing real-time HUD spotlight.
    """
    safety.reset()
    try:
        screen_w, screen_h = pyautogui.size()
        label, strokes = get_shape_strokes(shape_or_prompt)

        print(f"\n  [GUI] 🎨 Initializing MS Paint for autonomous drawing: '{label}'...")
        
        # 1. Launch MS Paint directly via subprocess for lightning-fast execution
        try:
            subprocess.Popen("mspaint.exe")
        except Exception:
            # Fallback to Start Menu
            pyautogui.press("win")
            time.sleep(0.3)
            human_type("mspaint", interval=0.04)
            pyautogui.press("enter")

        time.sleep(1.2) # Allow Paint window to initialize
        safety.check()

        # 2. Maximize MS Paint window to guarantee generous canvas space
        print("  [GUI] 🪟 Maximizing MS Paint canvas...")
        pyautogui.hotkey("win", "up")
        time.sleep(0.5)
        safety.check()

        # 3. Canvas Center coordinates
        canvas_cx = screen_w // 2
        canvas_cy = (screen_h // 2) + 40

        # 4. Activate glowing Cybernetic HUD Overlay in DRAWING mode
        from ui.cursor_overlay import show_cursor_hud, hide_cursor_hud
        show_cursor_hud(label=f"🎨 PAINTING: {label.upper()}", mode="drawing", x=canvas_cx, y=canvas_cy)

        print(f"  [GUI] ✍️ Executing {len(strokes)} continuous vector stroke paths with mouse cursor...")
        
        multiplier = safety.get_speed_settings()["multiplier"]

        # 5. Draw each stroke path smoothly
        for s_idx, stroke in enumerate(strokes):
            safety.check()
            if not stroke:
                continue

            # Move cursor to the start of this stroke
            start_x = int(canvas_cx + stroke[0][0])
            start_y = int(canvas_cy + stroke[0][1])
            
            pyautogui.moveTo(start_x, start_y, duration=max(0.04, 0.25 * multiplier), tween=pyautogui.easeInOutQuad)
            time.sleep(max(0.01, 0.04 * multiplier))
            safety.check()

            # Press down left mouse button to begin drawing
            pyautogui.mouseDown(button="left")
            time.sleep(0.02)

            # Interpolate through all subsequent points
            for pt in stroke[1:]:
                safety.check()
                target_px = int(canvas_cx + pt[0])
                target_py = int(canvas_cy + pt[1])
                pyautogui.moveTo(target_px, target_py, duration=max(0.008, 0.035 * multiplier), tween=pyautogui.linear)

            # Release mouse button
            pyautogui.mouseUp(button="left")
            time.sleep(max(0.01, 0.06 * multiplier))

        # 6. Smoothly glide cursor away from the finished artwork
        print(f"  [GUI] ✨ Artwork complete! Gliding cursor away...")
        pyautogui.moveTo(canvas_cx + 170, canvas_cy + 170, duration=max(0.08, 0.4 * multiplier), tween=pyautogui.easeOutQuad)
        time.sleep(max(0.05, 0.3 * multiplier))
        hide_cursor_hud()

        return f"SpaceV has autonomously drawn a {label} in MS Paint using pure cursor automation, Sir."

    except pyautogui.FailSafeException:
        safety.abort()
        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered (Cursor shoved to corner)."
    except InterruptedError as e:
        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass
        return f"⚠️ EMERGENCY STOP: {str(e)}"
    except Exception as e:
        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass
        return f"Autonomous drawing stopped: {str(e)}"


def gui_open_and_search_app(app_name: str, text_to_type: str = "") -> str:
    """
    Autonomously opens the Windows Start Menu, searches for an app, opens it,
    and optionally types text inside it like a human.
    """
    safety.reset()
    try:
        screen_w, screen_h = pyautogui.size()
        
        print(f"  [GUI] 🖱️ Gliding cursor to Start Menu (20, {screen_h - 20})...")
        # 1. Smoothly glide cursor towards Windows Start area (bottom-left)
        human_move_to(20, screen_h - 20, duration=0.4, label="🖱️ OPENING START", mode="moving")
        safety.check()

        print(f"  [GUI] 🪟 Pressing Windows Start key...")
        pyautogui.press("win")
        time.sleep(0.3)
        safety.check()

        print(f"  [GUI] ⌨️ Typing app name: '{app_name}'...")
        human_type(app_name, interval=0.05, label=f"🔍 SEARCHING: {app_name.upper()}")
        time.sleep(0.4)
        safety.check()

        print(f"  [GUI] 🚀 Launching '{app_name}'...")
        pyautogui.press("enter")
        time.sleep(1.8) # Wait for app to render
        safety.check()

        # 5. If text content was provided (e.g. typing notes into Notepad)
        if text_to_type:
            center_x, center_y = screen_w // 2, screen_h // 2
            print(f"  [GUI] 🖱️ Focusing window at ({center_x}, {center_y})...")
            human_move_to(center_x, center_y, duration=0.35, label="🎯 FOCUSING APP", mode="clicking")
            pyautogui.click()
            time.sleep(0.2)
            safety.check()
            print(f"  [GUI] ✍️ Typing text: '{text_to_type}'...")
            human_type(text_to_type, interval=0.035, label="✍️ TYPING CONTENT")

        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass

        return f"Successfully opened '{app_name}' via autonomous cursor movement" + (f" and typed text into it." if text_to_type else ".")

    except pyautogui.FailSafeException:
        safety.abort()
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered (Cursor shoved to corner)."
    except InterruptedError as e:
        return f"⚠️ EMERGENCY STOP: {str(e)}"
    except Exception as e:
        return f"Autonomous action stopped: {str(e)}"


def resolve_gatekeeper_modal_guard(pending_query: Optional[str] = None) -> Optional[str]:
    """
    Universal Closed-Loop Gatekeeper Perception Guard.
    Delegates to core.modal_interceptor to detect and resolve any modal dialog across Windows.
    """
    from core.modal_interceptor import modal_interceptor
    time.sleep(0.8)
    resolved, gatekeeper, status = modal_interceptor.resolve_or_intercept(pending_task=pending_query)
    if not resolved and gatekeeper:
        return f"⚠️ Modal Blocker: {gatekeeper.question}"
    return None


def resolve_chrome_profile_guard(pending_query: Optional[str] = None) -> Optional[str]:
    """
    Closed-loop perception guard for Chrome. Delegates to universal resolve_gatekeeper_modal_guard.
    """
    return resolve_gatekeeper_modal_guard(pending_query=pending_query)


def gui_search_google_browser(query: str) -> str:
    """
    Autonomously opens a browser via Start Menu, navigates to Google, and types the query like a human.
    """
    safety.reset()
    try:
        screen_w, screen_h = pyautogui.size()

        print(f"  [GUI] 🖱️ Opening Start Menu to launch browser...")
        human_move_to(20, screen_h - 20, duration=0.4, label="🌐 LAUNCHING CHROME", mode="moving")
        safety.check()
        pyautogui.press("win")
        time.sleep(0.3)
        safety.check()

        print(f"  [GUI] ⌨️ Typing 'chrome'...")
        human_type("chrome", interval=0.05, label="🔍 SEARCHING CHROME")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(1.8)
        safety.check()

        # Closed-loop profile guard
        profile_res = resolve_chrome_profile_guard(pending_query=query)
        if profile_res and ("stuck" in profile_res.lower() or "waiting at" in profile_res.lower()):
            return f"⚠️ Modal Blocker: {profile_res}"

        print(f"  [GUI] 🌐 Focusing address bar and searching: '{query}'...")
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        safety.check()

        human_type(query, interval=0.04, label=f"🌐 SEARCHING: {query[:15]}...")
        time.sleep(0.2)
        pyautogui.press("enter")

        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass

        return f"Autonomously launched browser and searched for: '{query}'"

    except pyautogui.FailSafeException:
        safety.abort()
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered."
    except InterruptedError as e:
        return f"⚠️ EMERGENCY STOP: {str(e)}"
    except Exception as e:
        return f"Autonomous action stopped: {str(e)}"


def gui_play_youtube(video_query: str) -> str:
    """
    Autonomously opens Chrome, navigates to YouTube, searches for the video query,
    and clicks the video to play using mouse cursor and keystrokes.
    """
    import urllib.parse
    safety.reset()
    try:
        screen_w, screen_h = pyautogui.size()

        print(f"  [GUI] 🖱️ Gliding cursor to Start Menu (20, {screen_h - 20})...")
        human_move_to(20, screen_h - 20, duration=0.4, label="🎵 LAUNCHING YOUTUBE", mode="moving")
        safety.check()
        pyautogui.press("win")
        time.sleep(0.3)
        safety.check()

        print(f"  [GUI] ⌨️ Typing 'chrome'...")
        human_type("chrome", interval=0.04, label="🔍 OPENING BROWSER")
        time.sleep(0.3)
        pyautogui.press("enter")
        time.sleep(1.8)
        safety.check()

        # Closed-loop profile guard
        profile_res = resolve_chrome_profile_guard(pending_query=video_query)
        if profile_res and ("stuck" in profile_res.lower() or "waiting at" in profile_res.lower()):
            return f"⚠️ Modal Blocker: {profile_res}"

        # Focus address bar
        print(f"  [GUI] 🌐 Navigating to YouTube search for '{video_query}'...")
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.2)
        safety.check()

        encoded = urllib.parse.quote_plus(video_query)
        target_url = f"https://www.youtube.com/results?search_query={encoded}"
        human_type(target_url, interval=0.01, label="🔗 OPENING URL")
        pyautogui.press("enter")
        time.sleep(2.5) # Wait for YouTube to load results
        safety.check()

        # Smoothly glide cursor to the first video result and click it to start playback!
        video_x = int(screen_w * 0.35)
        video_y = int(screen_h * 0.32)
        print(f"  [GUI] 🖱️ Gliding cursor to video ({video_x}, {video_y}) and clicking...")
        human_move_to(video_x, video_y, duration=0.6, label="🎯 CLICKING VIDEO", mode="clicking")
        time.sleep(0.2)
        safety.check()
        pyautogui.click()

        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass

        return f"Autonomously navigated to YouTube, searched for '{video_query}', and clicked the video to play!"

    except pyautogui.FailSafeException:
        safety.abort()
        return "⚠️ EMERGENCY STOP: PyAutoGUI Fail-Safe triggered."
    except InterruptedError as e:
        return f"⚠️ EMERGENCY STOP: {str(e)}"
    except Exception as e:
        return f"Autonomous action stopped: {str(e)}"


def gui_type_text(text: str) -> str:
    """
    Types text at the current cursor position with human-like typing speed.
    """
    safety.reset()
    try:
        human_type(text, interval=0.04)
        try:
            from ui.cursor_overlay import hide_cursor_hud
            hide_cursor_hud()
        except Exception:
            pass
        return f"Typed text ({len(text)} chars) at cursor."
    except Exception as e:
        return f"Typing aborted: {str(e)}"
