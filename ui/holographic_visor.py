"""
SpaceV Iron-Man Holographic Desktop Visor (HUD Layer).
Full-screen, frameless, 100% click-through transparent amber/gold overlay.
Provides cinematic Mark 85 HUD corner brackets, subtle warm visor tint,
and dynamic targeting reticles without intercepting mouse clicks.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("SpaceV.HolographicVisor")

try:
    from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSlot
    from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPen
    from PyQt6.QtWidgets import QApplication, QWidget

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    QWidget = object  # type: ignore


class HolographicVisor(QWidget):
    """
    Full-Screen Click-Through Iron Man Visor Canvas.
    Renders ambient amber/gold tint, cybernetic corner brackets,
    and visual grounding target boxes over active applications.
    """

    _instance: Optional["HolographicVisor"] = None

    @classmethod
    def get_instance(cls) -> Optional["HolographicVisor"]:
        if cls._instance is None and PYQT_AVAILABLE:
            if not QApplication.instance():
                return None
            cls._instance = HolographicVisor()
        return cls._instance

    def __init__(self, parent=None):
        if not PYQT_AVAILABLE:
            logger.warning("[HOLOGRAPHIC_VISOR] PyQt6 not available; visor disabled")
            return

        super().__init__(parent)

        # 1. OS Window Flags: Frameless, Always-On-Top, Invisible in Taskbar, Never Takes Focus
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowTransparentForInput
        )

        # 2. Qt Attributes: Full Click-Through & Alpha Transparency
        # THIS GUARANTEES CLICKS PASS DIRECTLY TO YOUR BROWSER / VS CODE
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        # 3. Visor Aesthetic Parameters (Light Yellow / Amber Warm Gold)
        # 16 / 255 = ~6.3% opacity: subtle, cinematic, zero eye-strain
        self.tint_color = QColor(255, 175, 40, 16)
        self.hud_amber = QColor(255, 165, 0, 200)  # Neon Orange/Amber for Reticles
        self.hud_gold = QColor(255, 215, 0, 140)  # Golden Accents

        # 4. State Management
        self._is_active = False
        self._target_boxes: List[Dict] = []
        self._pulse_alpha = 1.0
        self._pulse_dir = -1
        self._attention_msg: Optional[str] = None

        # 5. Position & Geometry
        self.sync_screen_geometry()

        # 6. Smooth 60 FPS Breathing / Animation Loop (16ms)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self._on_tick)
        self.anim_timer.start(16)

    def sync_screen_geometry(self):
        """Sizes canvas to cover the full primary screen."""
        app = QApplication.instance()
        if not app:
            return
        screen = app.primaryScreen()
        if not screen:
            return
        geom = screen.geometry()
        self.setGeometry(geom)

    def set_tint_opacity(self, alpha_percent: int):
        """Adjusts the warm tint intensity (0 to 100). Default is 6-8%."""
        clamped = max(0, min(alpha_percent, 100))
        alpha_byte = int((clamped / 100.0) * 255)
        self.tint_color.setAlpha(alpha_byte)
        self.update()

    def highlight_target(self, x: int, y: int, w: int, h: int, label: str = "TARGET LOCK", duration_ms: int = 3000):
        """Draws an animated Iron Man targeting reticle around a button or window."""
        box = {
            "rect": QRectF(x, y, w, h),
            "label": label,
            "ttl": duration_ms / 16.0,  # frames remaining
        }
        self._target_boxes.append(box)
        self.update()

    def highlight_elements(self, elements: List[Dict[str, Any]], duration_ms: int = 25000):
        """
        Renders multiple interactive amber HUD target reticles simultaneously over on-screen elements.
        elements: [{"rect": QRectF(...) or (x, y, w, h), "label": "[1] Option A"}, ...]
        """
        self._target_boxes.clear()
        frames = duration_ms / 16.0
        for el in elements:
            r = el.get("rect")
            if isinstance(r, (tuple, list)) and len(r) == 4:
                rect_obj = QRectF(float(r[0]), float(r[1]), float(r[2]), float(r[3]))
            elif isinstance(r, QRectF):
                rect_obj = r
            else:
                continue

            self._target_boxes.append({
                "rect": rect_obj,
                "label": el.get("label", "TARGET LOCK"),
                "ttl": frames,
            })
        self.update()

    def highlight_modal_elements(
        self,
        options: List[Tuple[str, str]],
        hwnd: Optional[int] = None,
        window_rect: Optional[Tuple[int, int, int, int]] = None
    ):
        """
        Dynamically grounds interactive options on screen using UI Automation / OCR,
        projecting numbered cybernetic amber reticles over every card or button.
        """
        elements: List[Dict[str, Any]] = []

        try:
            from core.uia_grounding import find_control_by_name
        except Exception:
            find_control_by_name = None

        try:
            from core.vision_grounding import find_text_coordinates
        except Exception:
            find_text_coordinates = None

        card_w, card_h = 160, 200

        for idx, (label, val) in enumerate(options, 1):
            clean_name = re.sub(r"^[^\w\s]+", "", label).strip()
            base_label = clean_name.split("(")[0].strip()
            num_label = f"[{idx}] {base_label}"

            coord = None
            if find_control_by_name and hwnd:
                res = find_control_by_name(base_label, hwnd=hwnd)
                if res:
                    coord = (res[0], res[1])

            if not coord and find_text_coordinates:
                res = find_text_coordinates(base_label)
                if res:
                    coord = (res[0], res[1])

            if coord:
                cx, cy = coord
                rx = max(0, cx - card_w // 2)
                ry = max(0, cy - card_h // 2)
                elements.append({
                    "rect": QRectF(float(rx), float(ry), float(card_w), float(card_h)),
                    "label": num_label
                })

        # Fallback: Construct an adaptive multi-element grid over the window if controls weren't individually found
        if not elements and window_rect:
            wx, wy, ww, wh = window_rect
            n = len(options)
            if n > 0:
                cols = min(n, 3)
                rows = (n + cols - 1) // cols
                spacing_x = ww // (cols + 1)
                spacing_y = wh // (rows + 1)
                for idx, (label, val) in enumerate(options, 1):
                    col = (idx - 1) % cols
                    row = (idx - 1) // cols
                    cx = wx + (col + 1) * spacing_x
                    cy = wy + (row + 1) * spacing_y
                    clean_name = re.sub(r"^[^\w\s]+", "", label).strip()
                    elements.append({
                        "rect": QRectF(float(cx - card_w // 2), float(cy - card_h // 2), float(card_w), float(card_h)),
                        "label": f"[{idx}] {clean_name}"
                    })

        if elements:
            self.highlight_elements(elements, duration_ms=25000)
        elif window_rect:
            self.highlight_target(window_rect[0], window_rect[1], window_rect[2], window_rect[3], label="ROADBLOCK DETECTED", duration_ms=25000)

    def clear_targets(self):
        """Clears all active targeting reticles."""
        self._target_boxes.clear()
        self.update()

    def set_attention(self, message: str = "ATTENTION REQUIRED: USER INPUT"):
        """Activates high-priority amber attention state on the holographic visor."""
        clean = message.replace("⚠️ Modal Blocker:", "").strip().split("\n")[0]
        self._attention_msg = clean[:55]
        # Warm up the amber tint during attention
        self.tint_color = QColor(255, 140, 0, 32)
        self.update()

    def clear_attention(self):
        """Restores normal subtle amber visor state."""
        self._attention_msg = None
        self.tint_color = QColor(255, 175, 40, 16)
        self.update()

    def _on_tick(self):
        """Updates subtle HUD pulse and expires active targeting boxes."""
        # Gentle breathing pulse for the corner brackets
        self._pulse_alpha += self._pulse_dir * 0.008
        if self._pulse_alpha <= 0.65:
            self._pulse_dir = 1
        elif self._pulse_alpha >= 1.0:
            self._pulse_dir = -1

        # Age target boxes
        active = []
        for b in self._target_boxes:
            b["ttl"] -= 1
            if b["ttl"] > 0:
                active.append(b)
        self._target_boxes = active

        self.update()

    def paintEvent(self, event):
        """Renders the full-screen visor layer."""
        if not self._is_active:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()

        # ─── 1. FULL-SCREEN LIGHT YELLOW / AMBER TINT ─────────────────
        painter.fillRect(0, 0, w, h, QBrush(self.tint_color))

        # ─── 2. CYBERNETIC CORNER BRACKETS (Iron Man Visor Frame) ─────
        bracket_len = 45
        pen_corner = QPen(self.hud_amber, 2)
        pen_corner.setColor(QColor(255, 165, 0, int(180 * self._pulse_alpha)))
        painter.setPen(pen_corner)

        margin = 15

        # Top-Left Bracket
        painter.drawLine(margin, margin, margin + bracket_len, margin)
        painter.drawLine(margin, margin, margin, margin + bracket_len)

        # Top-Right Bracket
        painter.drawLine(w - margin, margin, w - margin - bracket_len, margin)
        painter.drawLine(w - margin, margin, w - margin, margin + bracket_len)

        # Bottom-Left Bracket
        painter.drawLine(margin, h - margin, margin + bracket_len, h - margin)
        painter.drawLine(margin, h - margin, margin, h - margin - bracket_len)

        # Bottom-Right Bracket
        painter.drawLine(w - margin, h - margin, w - margin - bracket_len, h - margin)
        painter.drawLine(w - margin, h - margin, w - margin, h - margin - bracket_len)

        # ─── 3. SUBTLE HUD TOP TECH LABELS ────────────────────────────
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.setPen(QPen(QColor(255, 215, 0, int(140 * self._pulse_alpha))))
        painter.drawText(margin + 6, margin + 14, "JARVIS // VISOR MARK 85")
        status_txt = f"PERCEPTION: {self._attention_msg.upper()}" if self._attention_msg else "SYSTEM: OPTICAL ENGAGED"
        painter.drawText(w - margin - 260, margin + 14, status_txt)

        # ─── 3.5. ATTENTION BANNER WHEN ROADBLOCK OCCURS ──────────────
        if self._attention_msg:
            banner_w = 460
            banner_h = 32
            bx = (w - banner_w) // 2
            by = 64
            painter.fillRect(bx, by, banner_w, banner_h, QBrush(QColor(25, 14, 0, 220)))
            painter.setPen(QPen(QColor(255, 165, 0, int(220 * self._pulse_alpha)), 1.5))
            painter.drawRect(bx, by, banner_w, banner_h)
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
            painter.setPen(QColor(255, 200, 50, 255))
            painter.drawText(QRectF(bx, by, banner_w, banner_h), Qt.AlignmentFlag.AlignCenter, f"⚠️ {self._attention_msg}")

        # ─── 4. ACTIVE TARGETING BOXES / RETICLES (Warm Amber & Gold) ──
        for b in self._target_boxes:
            rect = b["rect"]
            label = b["label"]

            # Pulsing Warm Amber/Gold target box
            pen_target = QPen(QColor(255, 175, 40, int(210 * self._pulse_alpha)), 1.5, Qt.PenStyle.DashLine)
            painter.setPen(pen_target)
            painter.drawRect(rect)

            # Solid Gold Corner Accents on the target box
            pen_acc = QPen(self.hud_amber, 2.5)
            painter.setPen(pen_acc)
            c_len = min(16, max(6, int(rect.width() / 4)), max(6, int(rect.height() / 4)))

            # Box Top-Left
            painter.drawLine(int(rect.left()), int(rect.top()), int(rect.left() + c_len), int(rect.top()))
            painter.drawLine(int(rect.left()), int(rect.top()), int(rect.left()), int(rect.top() + c_len))
            # Box Top-Right
            painter.drawLine(int(rect.right()), int(rect.top()), int(rect.right() - c_len), int(rect.top()))
            painter.drawLine(int(rect.right()), int(rect.top()), int(rect.right()), int(rect.top() + c_len))
            # Box Bottom-Left
            painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.left() + c_len), int(rect.bottom()))
            painter.drawLine(int(rect.left()), int(rect.bottom()), int(rect.left()), int(rect.bottom() - c_len))
            # Box Bottom-Right
            painter.drawLine(int(rect.right()), int(rect.bottom()), int(rect.right() - c_len), int(rect.bottom()))
            painter.drawLine(int(rect.right()), int(rect.bottom()), int(rect.right()), int(rect.bottom() - c_len))

            # Amber Badge Background & Golden Label
            badge_w = max(80.0, float(len(label) * 8 + 14))
            badge_rect = QRectF(rect.left(), max(0.0, rect.top() - 20.0), badge_w, 18.0)
            painter.fillRect(badge_rect, QBrush(QColor(24, 14, 0, 220)))
            painter.setPen(QPen(QColor(255, 180, 50, 240), 1))
            painter.drawRect(badge_rect)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.setPen(QColor(255, 215, 0, 255))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, label)

        painter.end()
