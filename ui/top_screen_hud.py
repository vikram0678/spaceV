"""
SpaceV Iron-Man Cybernetic Top-Screen HUD Ribbon (Volume I §9 & Volume III §27).
Frameless, translucent, always-on-top desktop overlay docked at the top center of the screen.
Provides real-time ambient awareness into agent perception, reasoning, tool execution, and
presents lively interactive Action Cards directly on the workstation.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("SpaceV.TopScreenHUD")

try:
    from PyQt6.QtCore import QPoint, QRectF, Qt, QTimer, pyqtSignal
    from PyQt6.QtGui import QColor, QFont, QPainter, QPen
    from PyQt6.QtWidgets import (
        QApplication,
        QFrame,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QVBoxLayout,
        QWidget,
    )
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    QWidget = object  # type: ignore


class TopScreenHUD(QWidget):
    """
    Real-time Cybernetic Top-Screen HUD Ribbon.
    Displays live agent state, active tool operations, and slide-down holographic action cards.
    """
    chat_requested = pyqtSignal()
    open_urls_requested = pyqtSignal(list)

    def __init__(self, parent=None):
        if not PYQT_AVAILABLE:
            logger.info("[TOP_SCREEN_HUD] PyQt6 not available; running in headless mode")
            return

        super().__init__(parent)

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedWidth(560)

        self._active_phase: str = "IDLE"
        self._status_text: str = "SpaceV Cybernetic Co-Pilot Online"
        self._action_items: List[Dict[str, Any]] = []
        self._is_expanded: bool = False

        self._init_ui()
        self.init_position()

    def _init_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(4)

        # ─── Top Ribbon Frame ──────────────────────────────────────────
        self.ribbon_frame = QFrame(self)
        self.ribbon_frame.setObjectName("TopRibbonFrame")
        self.ribbon_frame.setFixedHeight(46)
        self.ribbon_frame.setStyleSheet("""
            QFrame#TopRibbonFrame {
                background: rgba(10, 16, 26, 0.92);
                border: 1px solid rgba(0, 240, 255, 0.55);
                border-radius: 22px;
            }
        """)

        ribbon_layout = QHBoxLayout(self.ribbon_frame)
        ribbon_layout.setContentsMargins(14, 0, 14, 0)
        ribbon_layout.setSpacing(10)

        # ⚡ Glowing Arc Reactor Pulse Indicator
        self.reactor_badge = QLabel("⚡", self.ribbon_frame)
        self.reactor_badge.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        self.reactor_badge.setStyleSheet("color: #00f0ff; background: transparent;")
        ribbon_layout.addWidget(self.reactor_badge)

        # Phase Pill (e.g. [HARVESTING], [PERCEIVING], [BROWSER])
        self.phase_pill = QLabel("[ STANDBY ]", self.ribbon_frame)
        self.phase_pill.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        self.phase_pill.setStyleSheet("""
            color: #00f0ff;
            background: rgba(0, 240, 255, 0.12);
            border: 1px solid rgba(0, 240, 255, 0.35);
            border-radius: 10px;
            padding: 2px 8px;
        """)
        ribbon_layout.addWidget(self.phase_pill)

        # Status Message Label
        self.status_label = QLabel(self._status_text, self.ribbon_frame)
        self.status_label.setFont(QFont("Segoe UI", 10))
        self.status_label.setStyleSheet("color: #e6edf3; background: transparent;")
        ribbon_layout.addWidget(self.status_label, 1)

        # Chat Summon Button
        self.btn_chat = QPushButton("💬", self.ribbon_frame)
        self.btn_chat.setFixedSize(28, 28)
        self.btn_chat.setToolTip("Toggle Cybernetic Chat Window")
        self.btn_chat.setStyleSheet("""
            QPushButton {
                background: rgba(22, 27, 34, 0.85);
                border: 1px solid rgba(0, 240, 255, 0.35);
                border-radius: 14px;
                color: #00f0ff;
                font-size: 12px;
            }
            QPushButton:hover {
                background: rgba(0, 240, 255, 0.25);
                border: 1px solid #00f0ff;
            }
        """)
        self.btn_chat.clicked.connect(self.chat_requested.emit)
        ribbon_layout.addWidget(self.btn_chat)

        self.main_layout.addWidget(self.ribbon_frame)

        # ─── Slide-Down Action Card (Initially Hidden) ────────────────
        self.card_frame = QFrame(self)
        self.card_frame.setObjectName("ActionCardFrame")
        self.card_frame.setStyleSheet("""
            QFrame#ActionCardFrame {
                background: rgba(13, 20, 32, 0.95);
                border: 1px solid rgba(0, 240, 255, 0.40);
                border-radius: 14px;
            }
        """)
        self.card_layout = QVBoxLayout(self.card_frame)
        self.card_layout.setContentsMargins(14, 10, 14, 10)
        self.card_layout.setSpacing(8)

        self.card_title = QLabel("🎯 Discovery", self.card_frame)
        self.card_title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self.card_title.setStyleSheet("color: #58a6ff; background: transparent;")
        self.card_layout.addWidget(self.card_title)

        self.card_body = QLabel("", self.card_frame)
        self.card_body.setFont(QFont("Segoe UI", 9))
        self.card_body.setWordWrap(True)
        self.card_body.setStyleSheet("color: #c9d1d9; background: transparent;")
        self.card_layout.addWidget(self.card_body)

        # Action Buttons Row
        self.actions_row = QHBoxLayout()
        self.actions_row.setSpacing(8)

        self.btn_primary_action = QPushButton("🌐 Open All in Chrome", self.card_frame)
        self.btn_primary_action.setFixedHeight(28)
        self.btn_primary_action.setStyleSheet("""
            QPushButton {
                background: #238636;
                color: #ffffff;
                font-weight: bold;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
            }
            QPushButton:hover { background: #2ea043; }
        """)
        self.btn_primary_action.clicked.connect(self._on_primary_action_clicked)
        self.actions_row.addWidget(self.btn_primary_action)

        self.btn_dismiss_card = QPushButton("✖️ Dismiss", self.card_frame)
        self.btn_dismiss_card.setFixedHeight(28)
        self.btn_dismiss_card.setStyleSheet("""
            QPushButton {
                background: rgba(48, 54, 61, 0.8);
                color: #8b949e;
                border: none;
                border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover { background: #30363d; color: #f0f6fc; }
        """)
        self.btn_dismiss_card.clicked.connect(self.hide_action_card)
        self.actions_row.addWidget(self.btn_dismiss_card)

        self.card_layout.addLayout(self.actions_row)
        self.card_frame.hide()
        self.main_layout.addWidget(self.card_frame)

    def init_position(self):
        """Positions HUD docked horizontally at the top center of the screen."""
        if not PYQT_AVAILABLE:
            return
        app = QApplication.instance()
        if not app:
            return
        screen = app.primaryScreen()
        if not screen:
            return
        geom = screen.availableGeometry()
        x = geom.x() + (geom.width() - self.width()) // 2
        y = geom.y() + 10
        self.move(x, y)

    def update_phase(self, phase: str, message: str = ""):
        """Updates the glowing phase badge and status message."""
        if not PYQT_AVAILABLE:
            return
        self._active_phase = phase
        clean_phase = phase.strip().upper()
        self.phase_pill.setText(f"[ {clean_phase} ]")

        color_map = {
            "IDLE": ("#00f0ff", "rgba(0, 240, 255, 0.12)"),
            "STANDBY": ("#00f0ff", "rgba(0, 240, 255, 0.12)"),
            "THINKING": ("#e3b341", "rgba(227, 179, 65, 0.18)"),
            "HARVESTING": ("#3fb950", "rgba(63, 185, 80, 0.18)"),
            "BROWSER": ("#58a6ff", "rgba(88, 166, 255, 0.18)"),
            "PERCEIVING": ("#bc8cff", "rgba(188, 140, 255, 0.18)"),
            "CONTAINMENT": ("#f85149", "rgba(248, 81, 73, 0.18)"),
            "SPEAKING": ("#2ea043", "rgba(46, 160, 67, 0.18)"),
            "ATTENTION": ("#ff9900", "rgba(255, 153, 0, 0.22)"),
        }

        border_color, bg_color = color_map.get(clean_phase, ("#00f0ff", "rgba(0, 240, 255, 0.12)"))
        self.phase_pill.setStyleSheet(f"""
            color: {border_color};
            background: {bg_color};
            border: 1px solid {border_color};
            border-radius: 10px;
            padding: 2px 8px;
        """)

        if message:
            self._status_text = message
            self.status_label.setText(message[:65] + ("..." if len(message) > 65 else ""))

    def show_action_card(self, title: str, summary: str, urls: Optional[List[str]] = None, action_label: str = "🌐 Open in Chrome"):
        """Displays an interactive holographic action card under the top ribbon."""
        if not PYQT_AVAILABLE:
            return
        self.card_title.setText(f"🎯 {title}")
        self.card_body.setText(summary[:220] + ("..." if len(summary) > 220 else ""))
        self._action_items = urls or []

        if self._action_items:
            self.btn_primary_action.setText(action_label)
            self.btn_primary_action.show()
        else:
            self.btn_primary_action.hide()

        self.card_frame.show()
        self._is_expanded = True
        self.adjustSize()

    def hide_action_card(self):
        """Hides the slide-down action card."""
        if not PYQT_AVAILABLE:
            return
        self.card_frame.hide()
        self._is_expanded = False
        self.adjustSize()

    def _on_primary_action_clicked(self):
        if self._action_items:
            self.open_urls_requested.emit(self._action_items)
            self.hide_action_card()

