"""
Cybernetic Animated Arc Reactor Floating Desktop Widget.
Features live rotating energy rings, breathing core pulse, and state animations.
"""
import math

from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QBrush, QColor, QFont, QPainter, QPen, QRadialGradient
from PyQt6.QtWidgets import QMenu, QWidget

from config import BUBBLE_SIZE, THEME


class FloatingIcon(QWidget):
    clicked = pyqtSignal()
    clear_chat_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.drag_position = QPoint()
        self.is_dragging = False
        self.drag_start_pos = QPoint()

        self.state = "IDLE" # IDLE, REFLEX, REASONING, THINKING, LISTENING, SPEAKING, ALERT
        self.angle = 0.0
        self.pulse = 0.0

        # Frameless, transparent, stays always on top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(BUBBLE_SIZE + 20, BUBBLE_SIZE + 20)

        # 60 FPS Ultra-Smooth Animation Timer (Upgrade #46)
        self.anim_timer = QTimer(self)
        self.anim_timer.timeout.connect(self.animate_frame)
        self.anim_timer.start(16)

        self.init_position()

    def set_state(self, new_state: str):
        self.state = new_state
        self.update()

    def animate_frame(self):
        try:
            if self.state in ("REFLEX", "ALERT"):
                speed = 0.08
            elif self.state in ("THINKING", "REASONING"):
                speed = 0.05
            elif self.state == "SPEAKING":
                speed = 0.035
            else:
                speed = 0.018
            self.angle = (self.angle + speed) % (2 * math.pi)
            self.pulse = (self.pulse + 0.06) % (2 * math.pi)
            self.update()
        except KeyboardInterrupt:
            self.anim_timer.stop()
            import os
            os._exit(0)

    def init_position(self):
        screen = self.screen().availableGeometry()
        x = screen.x() + screen.width() - self.width() - 30
        y = screen.y() + screen.height() - self.height() - 30
        self.move(x, y)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        cx = self.width() / 2
        cy = self.height() / 2
        base_radius = BUBBLE_SIZE / 2
        breathe = math.sin(self.pulse) * 3.5

        # 1. Dynamic Outer Energy Halo
        glow_rad = base_radius + 10 + breathe
        glow = QRadialGradient(cx, cy, glow_rad)
        if self.state == "REFLEX":
            glow.setColorAt(0.0, QColor(255, 179, 0, 190))
            glow.setColorAt(0.7, QColor(255, 140, 0, 80))
        elif self.state == "ALERT":
            glow.setColorAt(0.0, QColor(255, 42, 109, 190))
            glow.setColorAt(0.7, QColor(255, 0, 50, 80))
        elif self.state == "LISTENING":
            glow.setColorAt(0.0, QColor(0, 230, 118, 170))
            glow.setColorAt(0.7, QColor(0, 180, 80, 70))
        elif self.state in ("THINKING", "REASONING"):
            glow.setColorAt(0.0, QColor(168, 85, 247, 180))
            glow.setColorAt(0.7, QColor(0, 240, 255, 90))
        elif self.state == "SPEAKING":
            glow.setColorAt(0.0, QColor(255, 185, 0, 160))
            glow.setColorAt(0.7, QColor(255, 120, 0, 70))
        else:
            glow.setColorAt(0.0, QColor(0, 240, 255, 140))
            glow.setColorAt(0.7, QColor(112, 0, 255, 60))
        glow.setColorAt(1.0, QColor(0, 0, 0, 0))

        painter.setBrush(QBrush(glow))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(QRectF(cx - glow_rad, cy - glow_rad, glow_rad * 2, glow_rad * 2))

        # 2. Main Arc Reactor Glassmorphism Body
        body_grad = QRadialGradient(cx - 3, cy - 3, base_radius)
        body_grad.setColorAt(0.0, QColor(30, 41, 59, 230))
        body_grad.setColorAt(0.8, QColor(13, 17, 23, 240))
        body_grad.setColorAt(1.0, QColor(2, 6, 23, 250))
        painter.setBrush(QBrush(body_grad))

        # Outer Neon Ring
        if self.state == "REFLEX":
            primary_color = QColor("#ffb300")
        elif self.state == "ALERT":
            primary_color = QColor("#ff2a6d")
        elif self.state == "LISTENING":
            primary_color = QColor("#00e676")
        elif self.state in ("THINKING", "REASONING"):
            primary_color = QColor("#a855f7")
        elif self.state == "SPEAKING":
            primary_color = QColor("#ffb900")
        else:
            primary_color = QColor("#00f0ff")

        painter.setPen(QPen(primary_color, 2))
        painter.drawEllipse(QRectF(cx - base_radius, cy - base_radius, base_radius * 2, base_radius * 2))

        # 3. Rotating Segmented Reactor Ticks (Arc Reactor Markings)
        num_ticks = 8
        tick_radius = base_radius - 5
        painter.setPen(QPen(QColor(primary_color.red(), primary_color.green(), primary_color.blue(), 190), 2))

        for i in range(num_ticks):
            theta = self.angle + (i * (2 * math.pi / num_ticks))
            x1 = cx + math.cos(theta) * (tick_radius - 4)
            y1 = cy + math.sin(theta) * (tick_radius - 4)
            x2 = cx + math.cos(theta) * tick_radius
            y2 = cy + math.sin(theta) * tick_radius
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))

        # 4. Glowing Center Core Symbol
        painter.setPen(primary_color)
        font = QFont("Segoe UI", 15, QFont.Weight.Bold)
        painter.setFont(font)
        if self.state == "LISTENING":
            symbol = "🎙️"
        elif self.state == "SPEAKING":
            symbol = "🔊"
        elif self.state == "THINKING":
            symbol = "⚙️"
        else:
            symbol = "⚡"
        painter.drawText(QRectF(0, 0, self.width(), self.height()), Qt.AlignmentFlag.AlignCenter, symbol)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.drag_start_pos = event.globalPosition().toPoint()
            self.is_dragging = False
            event.accept()
        elif event.button() == Qt.MouseButton.RightButton:
            self.show_context_menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            distance = (event.globalPosition().toPoint() - self.drag_start_pos).manhattanLength()
            if distance > 4:
                self.is_dragging = True
                self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.is_dragging:
                self.clicked.emit()
            self.is_dragging = False
            event.accept()

    def show_context_menu(self, pos: QPoint):
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {THEME['bg_card']};
                color: {THEME['text_primary']};
                border: 1px solid {THEME['border_color']};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 20px;
                border-radius: 4px;
            }}
            QMenu::item:selected {{
                background-color: #1f6feb;
                color: #ffffff;
            }}
        """)

        toggle_action = QAction("💬 Toggle Chat Window", self)
        toggle_action.triggered.connect(self.clicked.emit)
        menu.addAction(toggle_action)

        clear_action = QAction("🧹 Clear Conversation", self)
        clear_action.triggered.connect(self.clear_chat_requested.emit)
        menu.addAction(clear_action)

        reset_action = QAction("📍 Reset Icon Position", self)
        reset_action.triggered.connect(self.init_position)
        menu.addAction(reset_action)

        menu.addSeparator()

        exit_action = QAction("❌ Exit SpaceV", self)
        exit_action.triggered.connect(self.exit_requested.emit)
        menu.addAction(exit_action)

        menu.exec(pos)
