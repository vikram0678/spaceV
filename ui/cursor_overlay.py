"""
Cybernetic Visual Laser Spotlight & Real-Time Cursor HUD Overlay.
Draws a buttery-smooth glowing neon reticle, rotating cybernetic ring,
and dynamic HUD badge tracking the mouse pointer at 60 FPS during autonomous actions.
"""
from PyQt6.QtCore import Q_ARG, QMetaObject, QRectF, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QCursor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QApplication, QWidget


class CursorOverlay(QWidget):
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = CursorOverlay()
        return cls._instance

    def __init__(self):
        super().__init__()
        # Click-through, transparent, stays on top of all windows
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool |
            Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        self.setFixedSize(160, 160)

        # Animation states
        self.pulse_phase = 0.0
        self.rot_angle = 0.0
        self.hud_label = "⚡ SPACEV ACTIVE"
        self.hud_mode = "moving"  # moving | drawing | clicking | typing
        self.target_x = 0
        self.target_y = 0
        self.current_x = 0
        self.current_y = 0
        self.fade_alpha = 0.0
        self.is_active = False

        # High-frequency 60 FPS real-time tracking & animation timer (16ms)
        self.track_timer = QTimer(self)
        self.track_timer.timeout.connect(self._on_tick)
        self.track_timer.start(16)

    @pyqtSlot(str, str)
    def start_hud(self, label: str = "⚡ SPACEV ACTIVE", mode: str = "moving"):
        """Activates and shows the cursor HUD overlay with target label and mode."""
        self.hud_label = label
        self.hud_mode = mode
        self.is_active = True

        # Initialize position to current mouse pointer
        pos = QCursor.pos()
        self.target_x = pos.x()
        self.target_y = pos.y()
        self.current_x = pos.x()
        self.current_y = pos.y()
        self.move(int(self.current_x - self.width() // 2), int(self.current_y - self.height() // 2))

        if not self.isVisible():
            self.show()
            self.raise_()

    @pyqtSlot()
    def stop_hud(self):
        """Signals the HUD overlay to fade out gracefully."""
        self.is_active = False

    @pyqtSlot(int, int)
    def update_position(self, global_x: int, global_y: int):
        """Explicitly sets target coordinates."""
        self.target_x = global_x
        self.target_y = global_y

    def _on_tick(self):
        """60 FPS loop tracking the mouse pointer and driving micro-animations."""
        # Update mouse coordinates
        pos = QCursor.pos()
        self.target_x = pos.x()
        self.target_y = pos.y()

        # Snappy LERP interpolation for buttery smooth glide
        self.current_x += (self.target_x - self.current_x) * 0.75
        self.current_y += (self.target_y - self.current_y) * 0.75

        # Handle smooth fade-in / fade-out
        if self.is_active:
            if self.fade_alpha < 1.0:
                self.fade_alpha = min(1.0, self.fade_alpha + 0.12)
        else:
            if self.fade_alpha > 0.0:
                self.fade_alpha = max(0.0, self.fade_alpha - 0.1)
            else:
                if self.isVisible():
                    self.hide()
                    return

        # Advance rotation & pulse animations
        self.rot_angle = (self.rot_angle + 3.0) % 360.0
        self.pulse_phase = (self.pulse_phase + 0.1) % 6.28

        # Move widget center directly onto cursor
        self.move(int(self.current_x - self.width() // 2), int(self.current_y - self.height() // 2))

        if self.isVisible():
            self.update()

    def paintEvent(self, event):
        if self.fade_alpha <= 0.01:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setOpacity(self.fade_alpha)

        cx = self.width() / 2
        cy = self.height() / 2

        # Choose theme palette based on mode
        if self.hud_mode == "drawing":
            primary_col = QColor("#c084fc")   # Electric Purple
            sec_col = QColor(168, 85, 247, 80)
            glow_col = QColor(192, 132, 252, 140)
        elif self.hud_mode == "clicking":
            primary_col = QColor("#f59e0b")   # Amber Gold
            sec_col = QColor(245, 158, 11, 80)
            glow_col = QColor(245, 158, 11, 140)
        elif self.hud_mode == "typing":
            primary_col = QColor("#10b981")   # Emerald Green
            sec_col = QColor(16, 185, 129, 80)
            glow_col = QColor(16, 185, 129, 140)
        else:
            primary_col = QColor("#00f0ff")   # Cyber Cyan
            sec_col = QColor(0, 240, 255, 80)
            glow_col = QColor(0, 240, 255, 140)

        # 1. Soft Outer Radial Glow
        pulse_r = 30 + (4 * (1 + 0.5 * (self.pulse_phase % 3.14)))
        glow = QRadialGradient(cx, cy, pulse_r + 20)
        glow.setColorAt(0.0, glow_col)
        glow.setColorAt(0.5, sec_col)
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))
        painter.setBrush(glow)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - pulse_r - 20, cy - pulse_r - 20, (pulse_r + 20) * 2, (pulse_r + 20) * 2))

        # 2. Outer Rotating Segmented Reticle Ring
        painter.save()
        painter.translate(cx, cy)
        painter.rotate(self.rot_angle)

        pen_ring = QPen(primary_col, 2.0, Qt.PenStyle.DashLine)
        pen_ring.setDashPattern([6, 4])
        painter.setPen(pen_ring)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(-pulse_r, -pulse_r, pulse_r * 2, pulse_r * 2))
        painter.restore()

        # 3. Inner Steady Ring
        inner_r = 18.0
        pen_inner = QPen(primary_col, 1.2, Qt.PenStyle.SolidLine)
        painter.setPen(pen_inner)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(QRectF(cx - inner_r, cy - inner_r, inner_r * 2, inner_r * 2))

        # 4. Precision Crosshair Notches (North, East, South, West)
        painter.setPen(QPen(primary_col, 1.8))
        notch_len = 7
        gap = 12
        # Top
        painter.drawLine(int(cx), int(cy - gap - notch_len), int(cx), int(cy - gap))
        # Bottom
        painter.drawLine(int(cx), int(cy + gap), int(cx), int(cy + gap + notch_len))
        # Left
        painter.drawLine(int(cx - gap - notch_len), int(cy), int(cx - gap), int(cy))
        # Right
        painter.drawLine(int(cx + gap), int(cy), int(cx + gap + notch_len), int(cy))

        # 5. Core Center Luminous Dot
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(primary_col)
        painter.drawEllipse(QRectF(cx - 3.5, cy - 3.5, 7, 7))

        # 6. Sleek HUD Glass Pill Badge Below Reticle
        pill_w = 136
        pill_h = 22
        pill_x = (self.width() - pill_w) / 2
        pill_y = cy + pulse_r + 4

        # Pill background
        painter.setBrush(QColor(13, 17, 23, 220))
        painter.setPen(QPen(primary_col, 1.0))
        painter.drawRoundedRect(QRectF(pill_x, pill_y, pill_w, pill_h), 11, 11)

        # Pill text
        painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
        painter.setPen(primary_col)
        painter.drawText(QRectF(pill_x, pill_y, pill_w, pill_h), Qt.AlignmentFlag.AlignCenter, self.hud_label)


def show_cursor_hud(label: str = "⚡ SPACEV ACTIVE", mode: str = "moving", x: int = None, y: int = None):
    """Thread-safe activation of the SpaceV Cursor HUD overlay."""
    app = QApplication.instance()
    if not app:
        return
    overlay = CursorOverlay.get_instance()
    if overlay:
        if x is not None and y is not None:
            QMetaObject.invokeMethod(overlay, "update_position", Qt.ConnectionType.QueuedConnection, Q_ARG(int, x), Q_ARG(int, y))
        QMetaObject.invokeMethod(overlay, "start_hud", Qt.ConnectionType.QueuedConnection, Q_ARG(str, label), Q_ARG(str, mode))


def hide_cursor_hud():
    """Thread-safe deactivation of the SpaceV Cursor HUD overlay."""
    app = QApplication.instance()
    if not app:
        return
    overlay = CursorOverlay.get_instance()
    if overlay:
        QMetaObject.invokeMethod(overlay, "stop_hud", Qt.ConnectionType.QueuedConnection)
